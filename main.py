import logging
import time
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram import Update

import rollbot_secret_token
from helper_functions import *
from database import CustomRoll, GlobalRoll

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO, filename="data/rollbot.log")
logger = logging.getLogger(__name__)


class Rollbot(Helper):
    def __init__(self):
        super().__init__()
        self.start_time = time.time()
        self.pending_rolls = []
        self.global_commands = {
            'ping': self.ping,
            'r': self.simple_roll,
            'c': self.custom_roll_wrapper(3, 6),
            'd': self.equation_roll,
            'stats': self.get_stats,
            'statsall': self.get_full_stats,
            'help': self.help_handler,
            'add': self.add_command_handler,
            'remove': self.remove_command_handler,
            'list': self.list_command_handlers,
            'commit': self.db_commit,
            'add_global': self.add_global_command,
            'remove_global': self.remove_global_command,
            'get_globals': self.get_global_commands,
            'get': self.get_command_usage,
            'reset': self.reset_command_usage
        }

    def stop(self):
        self.db.close()

    def custom_roll_wrapper(self, cnt, dice):
        return lambda update, context: self.simple_roll(update, context, cnt, dice)

    # params: update and context
    def simple_roll(self, update: Update, context, cnt=1, rolls_dice=20, mod_act=None, mod_num=None):
        parsed = self.parse_simple_roll(update.message.text, cnt, rolls_dice, mod_act, mod_num, context.bot.name)
        command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed

        try:
            # get numbers and generate text
            rolls = [self.rnd(rolls_dice) for _ in range(rolls_cnt)]
            rolls_info = ' + '.join(str(r) for r in rolls)
            if mod_act is not None:
                if mod_num == 'h':
                    rolls_info = 'Max of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(max(rolls))
                elif mod_num == 'l':
                    rolls_info = 'Min of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(min(rolls))
                elif self.sanity_bound(mod_num, self.ONLY_DIGITS) == len(mod_num) > 0:
                    # PyCharm says it's ok. I hope so
                    rolls_info = '(' + rolls_info + ') ' + mod_act + ' ' + mod_num + ' = ' + \
                                 str(eval(str(sum(rolls)) + mod_act + mod_num))
                else:
                    comment = mod_act + mod_num + comment
            text = self.get_user_name(update) + ': ' + comment + '\n' + rolls_info
            if rolls_cnt > 1 and mod_act is None:
                text += '\nSum: '
                if cnt != 1:
                    text += '(' \
                            + ') + ('.join(str(sum(rolls[i * cnt:(i + 1) * cnt])) for i in range(rolls_cnt // cnt)) \
                            + ') = '
                text += str(sum(rolls))
            self.reply_to_message(update, text)
            self.db.increment_counted_roll(update.message.chat_id, update.message.from_user.id, command_text)
        except Exception as e:
            update.message.reply_text("{}: {}\n{}".format(self.get_user_name(update), update.message.text[3:],
                                                          ' + '.join(str(self.rnd(rolls_dice)) for _ in range(cnt))))
            raise e

    def equation_roll(self, update, _):
        s, rolls, rest = self.roll_processing(update.message.text[2:])
        r = self.calc(s)
        self.reply_to_message(update, self.get_user_name(update) + ': ' + rest + '\n' + s + '\n' +
                              (r[1] if r[0] is None else (' = ' + str(r[0]))))

    # just ping
    @staticmethod
    def ping(update, _):
        update.message.reply_text('Pong!')
        print('ping!')

    def add_global_command(self, update, context):
        if update.message.from_user.id == self.MASTER_ID:
            if update.message.text.count(' ') != 2:
                self.reply_to_message(update, "Usage: /add_global /roll 1d20")
                return
            _, shortcut, roll = update.message.text.split()
            parsed = self.parse_simple_roll(shortcut + ' ' + roll, botname=context.bot.name)
            command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed
            roll = self.db.get_global_roll(shortcut)
            if roll is not None:
                self.reply_to_message(update, "Already has this command!")
            self.db.set_global_roll(GlobalRoll(shortcut, rolls_cnt, rolls_dice, mod_act, mod_num))
            msg = "Added command successfully!\n{} - {}d{}".format(shortcut, rolls_cnt, rolls_dice)
            if mod_act is not None:
                msg += mod_act + mod_num
            self.reply_to_message(update, msg)
        else:
            self.reply_to_message(update, "Access denied")

    def remove_global_command(self, update, _):
        if update.message.from_user.id == self.MASTER_ID:
            if update.message.text.count(' ') != 1:
                self.reply_to_message(update, "Usage: /remove_global /roll")
                return
            shortcut = update.message.text.split()[1]
            res = self.db.remove_global_roll(GlobalRoll(shortcut, 1, 20))
            if res > 0:
                msg = "Removed successfully!"
            else:
                msg = "Unknown command"
            self.reply_to_message(update, msg)
        else:
            self.reply_to_message(update, "Access denied")

    def get_global_commands(self, update, _):
        rolls = self.db.get_all_global_rolls()
        msg = "Global rolls:"
        for roll in rolls:
            msg += "\n/{} - {}d{}".format(roll.shortcut, roll.count, roll.dice)
            if roll.mod_act is not None:
                msg += roll.mod_act + roll.mod_num
        self.reply_to_message(update, msg)

    def get_command_usage(self, update, context):
        has_access, chat_id, target_id = self.is_user_has_stats_access(update, context, self.MASTER_ID)
        if has_access:
            rolls = list(filter(lambda r: r.chat_id == chat_id and r.user_id == target_id,
                                self.db.get_all_counted_rolls()))
            if len(rolls) == 0:
                self.reply_to_message(update, "Нет статистики для этого пользователя")
            else:
                msg = "Статистика:"
                for roll in rolls:
                    msg += "\n{} - {} раз".format(roll.command, roll.count)
                    self.reply_to_message(update, msg)

    def reset_command_usage(self, update, context):
        has_access, chat_id, target_id = self.is_user_has_stats_access(update, context, self.MASTER_ID)
        if has_access:
            cmds = update.message.text.split(' ', 1)
            if len(cmds) == 1:
                return self.reply_to_message(update, "Usage: /reset cmd")
            cmd = cmds[1]
            roll = self.db.get_counted_roll(chat_id, target_id, cmd)
            if roll is None:
                return self.reply_to_message(update, "Нечего сбрасывать")
            count = roll.count
            roll.count = 0
            self.db.set_counted_roll(roll)
            self.reply_to_message(update, "Сброшено. Старое значение: " + str(count))

    # get stats only to d20
    def get_stats(self, update, _):
        ts = update.message.text.split(' ', 2)
        if len(ts) > 1:
            dice = self.to_int(ts[1], default=20, max_v=1000000000)
        else:
            dice = 20
        stats = self.stats_to_dict()
        if dice in stats:
            overall = sum(stats[dice].values())
            msg = "Stats for this bot:\nUptime: {} hours\nd20 stats (%): from {} rolls".format(
                (time.time() - self.start_time) / 3600, overall)
            for i in range(1, dice + 1):
                if i in stats[dice]:
                    msg += "\n{0}: {1:.3f}".format(i, stats[dice][i] / overall * 100)
        else:
            msg = "No information for this dice!"
        self.reply_to_message(update, msg)

    # get all stats
    def get_full_stats(self, update, _):
        msg = "Stats for this bot:\nUptime: {} hours".format((time.time() - self.start_time) / 3600)
        stats = self.stats_to_dict()
        for key in sorted(stats.keys()):
            stat_sum = sum(stats[key])
            msg += "\nd{} stats (%): from {} rolls".format(key, stat_sum)
            for i in range(1, key + 1):
                if i in stats[key]:
                    addition = "\n{0}: {1:.3f}".format(i, stats[key][i] / stat_sum * 100)
                    if len(msg) + len(addition) > 4000:
                        self.reply_to_message(update, msg)
                        msg = ''
                    msg += addition
        self.reply_to_message(update, msg)

    def help_handler(self, update, _):
        if update.message.from_user.language_code == "ru":
            text = "Доступные команды:\n`/r 5d20+7`\\- рольнуть 5d20 и добавить 7\\. По умолчанию ролл 1d20\n" \
                   "`/r d20`, `/r 5` и `/r +7` тоже принимаются\nЕще принимает: `/c` \\- по умолчанию 3d6\n" \
                   "`/s` \\- 1d11\n`/p` \\- 1d100\n\n" \
                   "Ещё `/d *уравнение*` \\- вычислить \\*уравнение\\* с роллами дайсов\n\n" \
                   "Персональные команды: `/add` а потом комманда\\. Например: `/2d6_1 2d6+1`\n" \
                   "`/remove cmd` \\- удалить cmd из списка персональных команд\n`/list` \\- список персональных команд\n" \
                   "\n/stats N \\- получить статистику для роллов дайса N\n/statsall \\- получить статистику всех бросков" \
                   "`/get_globals` \\- get all global rolls"
        else:
            text = "Available commands:\n`/r 5d20+7`\\- roll 5d20 and add 7\\. Default dice is 1d20\n" \
                   "`/r d20` and `/r 5` and `/r +7` are fine too\nAlso can understand: `/c` \\- default 3d6\n" \
                   "`/s` \\- 1d11\n`/p` \\- 1d100\n\n" \
                   "And `/d *equation*` \\- evaluate \\*equation\\* with dice rolls in it\n\n" \
                   "Custom commands: `/add` and then your command like you\\'d to see\\. For example: `/2d6_1 2d6+1`\n" \
                   "`/remove cmd` \\- delete cmd from your commands\n`/list` \\- list of your commands\n\n" \
                   "/stats N \\- get statistic for dice N\n/statsall \\- get full statistic\n" \
                   "`/get_globals` \\- get all global rolls"
        if update.message.from_user.id == self.MASTER_ID:
            text += "\n\n`/add_global /roll 1d20` \\- add new global roll\n`/remove_global /roll` \\- remove global roll\n"
        self.reply_to_message(update, text, is_markdown=True)

    def add_command_handler(self, update, _):
        user_id = update.message.from_user.id
        if user_id not in self.pending_rolls:
            self.pending_rolls.append(user_id)
        self.reply_to_message(update, "Ok, now send me command and what it will stands for\\. For example: `/2d6_1 2d6 + 1`",
                              is_markdown=True)

    def remove_command_handler(self, update, context):
        user_id = update.message.from_user.id
        ts = update.message.text.split()
        if len(ts) == 2:
            cmd = ts[1].replace(context.bot.name, '').lstrip('/')
            if len(cmd) > 0:
                custom_roll = self.db.get_custom_roll(user_id, cmd)
                if custom_roll is not None:
                    self.db.remove_custom_roll(custom_roll)
                    self.reply_to_message(update, "Deleted {} successfully!".format(cmd))
                else:
                    self.reply_to_message(update, "No command named {} found!".format(cmd))
        else:
            self.reply_to_message(update, "Usage: `/remove your_cmd`", is_markdown=True)

    def list_command_handlers(self, update, _):
        user_id = update.message.from_user.id
        custom_rolls = list(filter(lambda c_roll: c_roll.user_id == user_id, self.db.get_all_custom_rolls()))
        if len(custom_rolls) == 0:
            self.reply_to_message(update, "You have no custom commands")
        else:
            msg = "Your commands:"
            for custom_roll in custom_rolls:
                msg += "\n/{} - {}d{}".format(custom_roll.shortcut, custom_roll.count, custom_roll.dice)
                if custom_roll.mod_act is not None:
                    msg += custom_roll.mod_act + custom_roll.mod_num
            if user_id in self.pending_rolls:
                msg += "Pending custom command to add"
            self.reply_to_message(update, msg)

    def all_commands_handler(self, update, context):
        if update.message.text is None or len(update.message.text) == 0 or update.message.text[0] != '/':
            return  # Not a command
        user_id = update.message.from_user.id
        cmd = update.message.text.split()[0][1:].replace(context.bot.name, '').lstrip('/')
        roll = self.db.get_global_roll(cmd)
        if roll is not None:
            return self.simple_roll(update, context, roll.count, roll.dice, roll.mod_act, roll.mod_num)
        if user_id in self.pending_rolls:
            parsed = self.parse_simple_roll(update.message.text, botname=context.bot.name)
            command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed
            if ' ' in command_text:
                self.db.set_custom_roll(CustomRoll(user_id, cmd, rolls_cnt, rolls_dice, mod_act, mod_num))
                self.pending_rolls.remove(user_id)
                msg = "Added command successfully!\n{} - {}d{}".format(cmd, rolls_cnt, rolls_dice)
                if mod_act is not None:
                    msg += mod_act + mod_num
                self.reply_to_message(update, msg)
            else:
                self.reply_to_message(update, "Need arguments for command\\. For example: `/2d6_1 2d6+1`",
                                      is_markdown=True)
        else:
            custom_roll = self.db.get_custom_roll(user_id, cmd)
            if custom_roll is not None:
                self.simple_roll(update, context, custom_roll.count, custom_roll.dice,
                                 custom_roll.mod_act, custom_roll.mod_num)

    def db_commit(self, update, _):
        if update.message.from_user.id == self.MASTER_ID:
            self.db.commit()
            update.message.reply_text("OK")

    # log all errors
    def error_handler(self, update: Update, context: CallbackContext):
        logger.error('Error: {} ({} {}) caused.by {}'.format(context, type(context.error), context.error, update))
        print("Error: " + str(context.error))
        if update is not None and update.message is not None:
            update.message.reply_text("Error")
            context.bot.send_message(chat_id=self.MASTER_ID, text="Error: {} {} for message {}".format(
                str(type(context.error))[:1000], str(context.error)[:2000], str(update.message.text)[:1000]))


# start
def init(token):
    if not os.path.exists('data'):
        os.makedirs('data')
    rollbot = Rollbot()

    updater = Updater(token=token, use_context=True)
    # adding handlers
    for command, func in rollbot.global_commands.items():
        updater.dispatcher.add_handler(CommandHandler(command, func))
    updater.dispatcher.add_handler(MessageHandler(Filters.text, rollbot.all_commands_handler))
    updater.dispatcher.add_error_handler(rollbot.error_handler)

    updater.start_polling()
    updater.idle()
    print("Stopping")
    rollbot.stop()


if __name__ == '__main__':
    print("Started", time.time())
    init(rollbot_secret_token.token)
