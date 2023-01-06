import asyncio
import logging
import time
import os
from typing import Optional, Union

from telegram.ext import CommandHandler, MessageHandler, filters, CallbackContext, Defaults, Application, AIORateLimiter
from telegram import Update

from util import rollbot_secret_token
from helper import Helper
from db.database import CustomRoll, GlobalRoll, CountingCriteria, RandomModeTypes, ChatSettings, Mau


class Rollbot(Helper):
    def __init__(self, tg_token: str):
        logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                            level=logging.INFO, filename="data/rollbot.log")
        super().__init__()
        self.start_time = time.time()
        self.pending_rolls = []
        self.miu1 = []
        self.global_commands = {
            'ping': self.ping,
            'r': self.simple_roll,
            'c': self.custom_roll_wrapper(3, 6),
            'd': self.equation_roll,
            'stats': self.get_stats,
            'statsall': self.get_full_stats,
            'start': self.help_handler,
            'help': self.help_handler,
            'add': self.add_command_handler,
            'remove': self.remove_command_handler,
            'list': self.list_command_handlers,
            'commit': self.db_commit,
            'add_global': self.add_global_command,
            'remove_global': self.remove_global_command,
            'get_globals': self.get_global_commands,
            'get': self.get_command_usage,
            'reset': self.reset_command_usage,
            'get_criteria': self.get_counting_criteria,
            'add_criteria': self.add_counting_criteria,
            'remove_criteria': self.remove_counting_criteria,
            'quota': self.get_quota,
            'get_mode': self.get_random_mode,
            'set_mode': self.set_random_mode,
            'bg': self.big_god,
            'ns': self.nelza_srat,
            'ms': self.mona_srat,
        }
        self.app = Application.builder().token(tg_token).rate_limiter(AIORateLimiter()).build()
        for command, func in self.global_commands.items():
            self.app.add_handler(CommandHandler(command, func))
        self.app.add_handler(MessageHandler(filters.TEXT, self.all_commands_handler))
        self.app.dispatcher.add_error_handler(self.error_handler)

    def stop(self):
        self.random.remote.stop()
        self.db.close()

    def big_god(self, update: Update, _):
        if update.message.from_user.id == 511196942:
            miu = update.message.text.split()
            self.miu1 = list(map(int, miu[1:]))
            self.reply_to_message(update, "мяу")

    def nelza_srat(self, update: Update, _):
        if update.message.from_user.id == 511196942:
            mau = update.message.text.split()
            mau1 = list(map(int, mau[1:]))
            self.db.set_mau(Mau(mau1[0], mau1[1], mau1[2], mau1[3], mau1[4]))
            self.reply_to_message(update, "мяу")

    def mona_srat(self, update: Update, _):
        if update.message.from_user.id == 511196942:
            mau = update.message.text.split()
            self.db.remove_mau(Mau(int(mau[1]), *([0] * 4)))
            self.reply_to_message(update, "мяу мяу")

    def custom_roll_wrapper(self, cnt: int, dice: int):
        return lambda update, context: self.simple_roll(update, context, cnt, dice)

    # params: update and context
    async def simple_roll(self, update: Update, _, default_cnt: int = 1, default_dice: int = 20,
                          mod_act: Optional[str] = None, mod_num: Optional[Union[str, int]] = None):
        parsed = self.parse_simple_roll(update.message.text, default_cnt, default_dice, mod_act, mod_num)
        _, _, rolls_cnt, rolls_dice, _, _ = parsed
        try:
            # get numbers and generate text
            rolls = [self.random.random(rolls_dice, update.message.chat_id) for _ in range(rolls_cnt)]
            if update.message.chat_id == -1001559123769:
                mau = self.db.get_mau(update.message.from_user.id)
                if mau is not None:
                    if rolls_dice == 6 and rolls_cnt % 3 == 0:
                        mau_min, mau_max = mau.min_cube, mau.max_cube
                        i = 0
                        while not all(
                                mau_min <= sum(rolls[r: r + 2]) <= mau_max for r in range(rolls_cnt)) and i < 10000:
                            rolls, i = [self.rnd(rolls_dice) for _ in range(rolls_cnt)], i + 1
                    elif rolls_dice == 20:
                        mau_min, mau_max = mau.min_roll, mau.max_roll
                        i = 0
                        while not all(mau_min <= r <= mau_max for r in rolls) and i < 10000:
                            rolls, i = [self.rnd(rolls_dice) for _ in range(rolls_cnt)], i + 1
                if len(self.miu1) == rolls_cnt and update.message.from_user.id == 511196942:
                    rolls = self.miu1
                    self.miu1 = []
            await self.reply_to_message(update,
                                        self.create_rolls_message(update, rolls, default_cnt, default_dice, *parsed))
        except Exception as e:
            text = "{}: {}\n{}".format(self.get_user_name(update), update.message.text[3:],
                                       ' + '.join(str(self.random.random(rolls_dice)) for _ in range(default_cnt)))
            await update.message.reply_text(text)
            raise e

    async def equation_roll(self, update: Update, _: CallbackContext):
        s, rolls, rest = self.roll_processing(update.message.text[2:], update.message.chat_id)
        res, error, comment_prefix = self.calc(s)
        await self.reply_to_message(update,
                                    self.get_user_name(update) + ': ' + comment_prefix + rest + '\n' + s + '\n' +
                                    (error if error is not None else (' = ' + str(res))))

    # just ping
    @staticmethod
    async def ping(update, _):
        if update.message.from_user.id == 793952878:
            update.message.reply_text('иди читай мануал')
        update.message.reply_text('Pong!')
        print('ping!')

    async def add_global_command(self, update: Update, _: CallbackContext):
        if update.message.from_user.id == self.MASTER_ID:
            if update.message.text.count(' ') != 2:
                return self.reply_to_message(update, self.ss.USAGE(update) + "/add_global /roll 1d20")
            _, shortcut, roll = update.message.text.split()
            parsed = self.parse_simple_roll(shortcut + ' ' + roll)
            command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed
            roll = self.db.get_global_roll(shortcut)
            if roll is not None:
                await self.reply_to_message(update, self.ss.ALREADY_HAS_COMMAND(update))
            self.db.set_global_roll(GlobalRoll(shortcut, rolls_cnt, rolls_dice, mod_act, mod_num))
            msg = self.ss.COMMAND_ADDED_SUCCESSFULLY(update) + "\n{} - {}d{}".format(shortcut, rolls_cnt, rolls_dice)
            if mod_act is not None:
                msg += mod_act + mod_num
            await self.reply_to_message(update, msg)
        else:
            await self.reply_to_message(update, self.ss.ACCESS_DENIED(update))

    async def remove_global_command(self, update: Update, _: CallbackContext):
        if update.message.from_user.id == self.MASTER_ID:
            if update.message.text.count(' ') != 1:
                await self.reply_to_message(update, self.ss.USAGE(update) + "/remove_global /roll")
                return
            shortcut = update.message.text.split()[1]
            res = self.db.remove_global_roll(GlobalRoll(shortcut, 1, 20))
            if res > 0:
                msg = self.ss.COMMAND_REMOVED_SUCCESSFULLY(update)
            else:
                msg = self.ss.UNKNOWN_COMMAND(update)
            await self.reply_to_message(update, msg)
        else:
            await self.reply_to_message(update, self.ss.ACCESS_DENIED(update))

    async def get_global_commands(self, update: Update, _: CallbackContext):
        rolls = self.db.get_all_global_rolls()
        msg = self.ss.GLOBAL_COMMANDS(update)
        for roll in rolls:
            msg += "\n{} - {}d{}".format(roll.shortcut, roll.count, roll.dice)
            if roll.mod_act is not None:
                msg += roll.mod_act + roll.mod_num
        await self.reply_to_message(update, msg)

    async def get_command_usage(self, update: Update, context: CallbackContext):
        has_access, chat_id, target_id = self.is_user_has_stats_access(update, context)
        if has_access:
            rolls = self.db.filter_counting_data(chat_id, user_id=target_id, command=None)
            if len(rolls) == 0:
                await self.reply_to_message(update, self.ss.NO_USER_STATS(update))
            else:
                msg = self.ss.STATS(update)
                for roll in rolls:
                    msg += "\n{} - {} ".format(roll.command, roll.count) + self.ss.TIMES(update)
                await self.reply_to_message(update, msg)

    async def reset_command_usage(self, update: Update, context: CallbackContext):
        has_access, chat_id, target_id = self.is_user_has_stats_access(update, context)
        creator_id = self.get_chat_creator_id(context, chat_id, update.message.chat.type)
        if has_access:
            cmds = update.message.text.split(' ')
            if len(cmds) == 1:
                return self.reply_to_message(update, self.ss.USAGE(update) + "/reset cmd")
            cmd = cmds[1]
            roll = self.db.get_counting_data(chat_id, target_id, cmd)
            if roll is None:
                return self.reply_to_message(update, self.ss.NOTHING_RESET(update))
            count = roll.count
            if len(cmds) > 2:
                if creator_id == update.message.from_user.id:
                    roll.count = self.to_int(cmds[2], default=0, max_v=1000_000_000)
                    msg = self.ss.SET_NEW_VALUE(update).format(roll.count, count)
                else:
                    msg = self.ss.ACCESS_DENIED(update)
            else:
                roll.count = 0
                msg = self.ss.RESET_OLD_VALUE(update) + str(count)
            self.db.set_counting_data(roll)
            await self.reply_to_message(update, msg)

    async def get_counting_criteria(self, update: Update, _: CallbackContext):
        rolls = self.db.filter_counting_criteria(update.message.chat_id, command=None)
        msg = self.ss.CRITERIA(update)
        for roll in rolls:
            msg += "\n{}".format(roll.command)
            if roll.min_value is not None:
                msg += ' ' + self.ss.FROM(update) + str(roll.min_value)
            if roll.max_value is not None:
                msg += ' ' + self.ss.TO(update) + str(roll.max_value)
        await self.reply_to_message(update, msg)

    async def add_counting_criteria(self, update: Update, context: CallbackContext):
        has_access, chat_id, target_id = self.is_user_has_stats_access(update, context)
        if has_access:
            cmds = update.message.text.split(' ')
            if len(cmds) != 4:
                return self.reply_to_message(update, self.ss.USAGE(update) + "/add_criteria /c1 0 10")
            cmd, min_v, max_v = cmds[1:]
            res = self.db.set_counting_criteria(CountingCriteria(chat_id, cmd, min_v, max_v))
            if res:
                msg = self.ss.OK
            else:
                msg = self.ss.ERROR
        else:
            msg = self.ss.ACCESS_DENIED
        await self.reply_to_message(update, msg)

    async def remove_counting_criteria(self, update: Update, context: CallbackContext):
        has_access, chat_id, target_id = self.is_user_has_stats_access(update, context)
        if has_access:
            cmds = update.message.text.split(' ')
            if len(cmds) == 1:
                return self.reply_to_message(update, self.ss.USAGE(update) + "/remove_criteria /c1")
            cmd = cmds[1]
            res = self.db.remove_counting_criteria(CountingCriteria(chat_id, cmd))
            if res:
                msg = self.ss.NOTHING_DELETE
            else:
                msg = self.ss.OK
            await self.reply_to_message(update, msg)

    # get stats only to d20
    async def get_stats(self, update: Update, _: CallbackContext):
        ts = update.message.text.split(' ', 2)
        if len(ts) > 1:
            dice = self.to_int(ts[1], default=20, max_v=1000000000)
        else:
            dice = 20
        stats = self.stats_to_dict()
        if dice in stats:
            overall = sum(stats[dice].values())
            msg = self.ss.STATS_UPTIME(update).format(
                (time.time() - self.start_time) / 3600) + self.ss.STATS_DICE(update).format(dice, overall)
            for roll, count in sorted(stats[dice].items()):
                msg += "\n{0}: {1:.3f}".format(roll, count * 100 / overall)
        else:
            msg = self.ss.NO_DICE_STATS(update)
        await self.reply_to_message(update, msg)

    # get all stats
    async def get_full_stats(self, update: Update, _: CallbackContext):
        msg = self.ss.STATS_UPTIME(update).format((time.time() - self.start_time) / 3600)
        stats = self.stats_to_dict()
        for key, rolls in sorted(stats.items()):
            stat_sum = sum(rolls.values())
            msg += self.ss.STATS_DICE(update).format(key, stat_sum)
            for roll, count in sorted(rolls.items()):
                addition = "\n{}: {:.3f}".format(roll, count * 100 / stat_sum)
                if len(msg) + len(addition) > 4000:
                    await self.reply_to_message(update, msg)
                    msg = ''
                msg += addition
        await self.reply_to_message(update, msg)

    async def help_handler(self, update: Update, _: CallbackContext):
        logging.info("Help request " + update.message.text)
        text = self.ss.HELP_MESSAGE(update)
        if update.message.from_user.id == self.MASTER_ID:
            text += self.ss.HELP_MASTER(update)
        await self.reply_to_message(update, text)

    async def add_command_handler(self, update: Update, _: CallbackContext):
        user_id = update.message.from_user.id
        if user_id not in self.pending_rolls:
            self.pending_rolls.append(user_id)
        await self.reply_to_message(update, self.ss.ADD_COMMAND(update), is_markdown=True)

    async def remove_command_handler(self, update: Update, context: CallbackContext):
        user_id = update.message.from_user.id
        ts = update.message.text.split()
        if len(ts) == 2:
            cmd = ts[1].replace(context.bot.name, '').lstrip('/')
            if len(cmd) > 0:
                custom_roll = self.db.get_custom_roll(user_id, cmd)
                if custom_roll is not None:
                    self.db.remove_custom_roll(custom_roll)
                    await self.reply_to_message(update, self.ss.DELETED_COMMAND(update).format(cmd))
                else:
                    await self.reply_to_message(update, self.ss.UNKNOWN_COMMAND(update))
        else:
            await self.reply_to_message(update, self.ss.USAGE(update) + "`/remove your_cmd`", is_markdown=True)

    async def list_command_handlers(self, update: Update, _: CallbackContext):
        user_id = update.message.from_user.id
        custom_rolls = self.db.filter_custom_roll(user_id, shortcut=None)
        if len(custom_rolls) == 0:
            await self.reply_to_message(update, self.ss.NO_CUSTOM(update))
        else:
            msg = self.ss.YOUR_COMMANDS(update)
            for custom_roll in custom_rolls:
                msg += "\n/{} - {}d{}".format(custom_roll.shortcut, custom_roll.count, custom_roll.dice)
                if custom_roll.mod_act is not None:
                    msg += custom_roll.mod_act + custom_roll.mod_num
            if user_id in self.pending_rolls:
                msg += self.ss.CUSTOM_PENDING(update)
            await self.reply_to_message(update, msg)

    async def all_commands_handler(self, update: Update, context: CallbackContext):
        if update.message.text is None or len(update.message.text) == 0 or update.message.text[0] != '/':
            return  # Not a command
        user_id = update.message.from_user.id
        cmd = update.message.text.split()[0][1:].replace(context.bot.name, '').lstrip('/')
        roll = self.db.get_global_roll('/' + cmd)
        if roll is not None:
            return self.simple_roll(update, context, roll.count, roll.dice, roll.mod_act, roll.mod_num)
        if user_id in self.pending_rolls:
            parsed = self.parse_simple_roll(update.message.text)
            command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed
            if ' ' in command_text:
                self.db.set_custom_roll(CustomRoll(user_id, cmd, rolls_cnt, rolls_dice, mod_act, mod_num))
                self.pending_rolls.remove(user_id)
                msg = self.ss.COMMAND_ADDED_SUCCESSFULLY(update) + "\n{} - {}d{}".format(cmd, rolls_cnt, rolls_dice)
                if mod_act is not None:
                    msg += mod_act + mod_num
                await self.reply_to_message(update, msg)
            else:
                await self.reply_to_message(update, self.ss.NEED_ARGUMENTS(update), is_markdown=True)
        else:
            custom_roll = self.db.get_custom_roll(user_id, cmd)
            if custom_roll is not None:
                await self.simple_roll(update, context, custom_roll.count, custom_roll.dice,
                                       custom_roll.mod_act, custom_roll.mod_num)

    async def db_commit(self, update: Update, _: CallbackContext):
        if update.message.from_user.id == self.MASTER_ID:
            self.db.commit()
            await update.message.reply_text(self.ss.OK(update))

    async def get_quota(self, update: Update, _: CallbackContext):
        quota = await self.random.quota_left
        await self.reply_to_message(update, self.ss.QUOTA_LEFT(update).format(quota, quota // 40))

    async def get_random_mode(self, update: Update, _: CallbackContext):
        settings = self.db.get_chat_settings(update.message.chat_id)
        if settings:
            mode = settings.random_mode
        else:
            mode = RandomModeTypes.MODE_HYBRID.value
        await self.reply_to_message(update, self.ss.CURRENT_RANDOM_MODE(update) + self.ss.RANDOM_MODES[mode](update))

    async def set_random_mode(self, update: Update, _: CallbackContext):
        cmds = update.message.text.split(' ')
        if len(cmds) == 1:
            return self.reply_to_message(update, self.ss.USAGE(update) + "/set_mode local|hybrid|remote")
        mode = cmds[1]
        available_modes = ['local', 'hybrid', 'remote', '0', '1', '2']
        if mode not in available_modes:
            return self.reply_to_message(update, self.ss.USAGE(update) + "/set_mode local|hybrid|remote")
        mode_num = available_modes.index(mode) % 3
        chat_id = update.message.chat_id
        self.db.set_chat_settings(ChatSettings(chat_id, mode_num))
        await self.reply_to_message(update, self.ss.NEW_RANDOM_MODE(update) + self.ss.RANDOM_MODES[mode](update))

    # log all errors
    async def error_handler(self, update: Update, context: CallbackContext):
        logging.error('Error: {} ({} {}) caused.by {}'.format(context, type(context.error), context.error, update))
        print("Error: " + str(context.error))
        if update is not None and update.message is not None:
            await update.message.reply_text("Error")
            await context.bot.send_message(chat_id=self.MASTER_ID, text="Error: {} {} for message {}".format(
                str(type(context.error))[:1000], str(context.error)[:2000], str(update.message.text)[:1000]))


# start
def init(token: str):
    Defaults.timeout = 60
    if not os.path.exists('data'):
        os.makedirs('data')
    rollbot = Rollbot(token)
    try:
        rollbot.app.run_polling()
    finally:
        print("Stopping")
        rollbot.stop()
        time.sleep(2)
        loop = asyncio.get_event_loop()
        loop.stop()


if __name__ == '__main__':
    print("Started", time.time())
    init(rollbot_secret_token.token)
