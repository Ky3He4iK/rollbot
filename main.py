import logging
import time
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext
from telegram import Update

import rollbot_secret_token
from helper_functions import *
from database import Database, Stat, CustomRoll, CountedRoll, GlobalRoll

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO, filename="rollbot.log")

logger = logging.getLogger(__name__)
db = Database()
start_time = time.time()
pending_rolls = []
global_commands = {}
MASTER_ID = 351693351


# returns an integer from 1 to dice inclusively and add result to stats
def rnd(dice: int) -> int:
    dice = abs(dice)  # remove negative values
    if dice == 0 or dice > 1000000:
        dice = 20  # remove incorrect
    res = get_random_num(dice)
    db.increment_stat(dice, res)
    return res


# params: update and context
def simple_roll(update: Update, _, cnt=1, rolls_dice=20, mod_act=None, mod_num=None):
    parsed = parse_simple_roll(update.message.text, cnt, rolls_dice, mod_act, mod_num)
    command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed

    try:
        # get numbers and generate text
        rolls = [rnd(rolls_dice) for _ in range(rolls_cnt)]
        rolls_info = ' + '.join(str(r) for r in rolls)
        if mod_act is not None:
            if mod_num == 'h':
                rolls_info = 'Max of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(max(rolls))
            elif mod_num == 'l':
                rolls_info = 'Min of (' + ', '.join(str(r) for r in rolls) + ') is ' + str(min(rolls))
            elif sanity_bound(mod_num, ONLY_DIGITS) == len(mod_num) > 0:  # PyCharm says it's ok. I hope so
                rolls_info = '(' + rolls_info + ') ' + mod_act + ' ' + mod_num + ' = ' + \
                             str(eval(str(sum(rolls)) + mod_act + mod_num))
            else:
                comment = mod_act + mod_num + comment
        text = get_user_name(update) + ': ' + comment + '\n' + rolls_info
        if rolls_cnt > 1 and mod_act is None:
            text += '\nSum: '
            if cnt != 1:
                text += '(' + ') + ('.join(str(sum(rolls[i * cnt:(i + 1) * cnt])) for i in range(rolls_cnt // cnt)) \
                        + ') = '
            text += str(sum(rolls))
        reply_to_message(update, text)
        db.increment_counted_roll(update.message.chat_id, update.message.from_user.id, command_text)
    except Exception as e:
        update.message.reply_text("{}: {}\n{}".format(get_user_name(update), update.message.text[3:],
                                                      ' + '.join(str(rnd(rolls_dice)) for _ in range(cnt))))
        raise e


def custom_roll_wrapper(cnt, dice):
    return lambda update, context: simple_roll(update, context, cnt, dice)


def equation_roll(update, _):
    s, rolls, rest = roll_processing(update.message.text[2:], random_generator=rnd)
    r = calc(s)
    reply_to_message(update, get_user_name(update) + ': ' + rest + '\n' + s + '\n' +
                     (r[1] if r[0] is None else (' = ' + str(r[0]))))


# just ping
def ping(update, _):
    update.message.reply_text('Pong!')
    print('ping!')


def add_global_command(update, _):
    if update.message.from_user.id == MASTER_ID:
        if update.message.text.count(' ') != 2:
            reply_to_message(update, "Usage: /add_global /roll 1d20")
            return
        _, shortcut, roll = update.message.text.split()
        parsed = parse_simple_roll(shortcut + ' ' + roll)
        command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed
        db.set_global_roll(GlobalRoll(shortcut, rolls_cnt, rolls_dice, mod_act, mod_num))
        msg = "Added command successfully!\n{} - {}d{}".format(shortcut, rolls_cnt, rolls_dice)
        if mod_act is not None:
            msg += mod_act + mod_num
        reply_to_message(update, msg)
    else:
        reply_to_message(update, "Access denied")


def remove_global_command(update, _):
    if update.message.from_user.id == MASTER_ID:
        if update.message.text.count(' ') != 1:
            reply_to_message(update, "Usage: /remove_global /roll")
            return
        shortcut = update.message.text.split()[1]
        res = db.remove_global_roll(GlobalRoll(shortcut, 1, 20))
        if res > 0:
            msg = "Removed successfully!"
        else:
            msg = "Unknown command"
        reply_to_message(update, msg)
    else:
        reply_to_message(update, "Access denied")


def get_global_commands(update, _):
    rolls = db.get_all_global_rolls()
    msg = "Global rolls:"
    for roll in rolls:
        msg += "\n/{} - {}d{}".format(roll.shortcut, roll.count, roll.dice)
        if roll.mod_act is not None:
            msg += roll.mod_act + roll.mod_num
    reply_to_message(update, msg)


def get_command_usage(update, context):
    chat_id, user_id = update.message.chat_id, update.message.from_user.id
    if user_id == MASTER_ID or (chat_id != user_id and get_chat_creator_id(context, chat_id) == user_id):
        pass  # todo
    else:
        reply_to_message(update, "Только создатель чата имеет доступ")


def reset_command_usage(update, context):
    chat_id, user_id = update.message.chat_id, update.message.from_user.id
    if user_id == MASTER_ID or (chat_id != user_id and get_chat_creator_id(context, chat_id) == user_id):
        pass  # todo
    else:
        reply_to_message(update, "Только создатель чата имеет доступ")


def stats_to_dict():
    stats = {}
    for stat in db.get_all_stats():
        if stat.dice not in stats:
            stats[stat.dice] = {}
        stats[stat.dice][stat.result] = stat.count
    return stats


# get stats only to d20
def get_stats(update, _):
    ts = update.message.text.split(' ', 2)
    if len(ts) > 1:
        dice = to_int(ts[1], default=20, max_v=1000000000)
    else:
        dice = 20
    stats = stats_to_dict()
    if dice in stats:
        overall = sum(stats[dice].values())
        msg = "Stats for this bot:\nUptime: {} hours\nd20 stats (%): from {} rolls".format(
            (time.time() - start_time) / 3600, overall)
        for i in range(1, dice + 1):
            if i in stats[dice]:
                msg += "\n{0}: {1:.3f}".format(i, stats[dice][i] / overall * 100)
    else:
        msg = "No information for this dice!"
    reply_to_message(update, msg)


# get all stats
def get_full_stats(update, _):
    msg = "Stats for this bot:\nUptime: {} hours".format((time.time() - start_time) / 3600)
    stats = stats_to_dict()
    for key in sorted(stats.keys()):
        stat_sum = sum(stats[key])
        msg += "\nd{} stats (%): from {} rolls".format(key, stat_sum)
        for i in range(1, key + 1):
            if i in stats[key]:
                addition = "\n{0}: {1:.3f}".format(i, stats[key][i] / stat_sum * 100)
                if len(msg) + len(addition) > 4000:
                    reply_to_message(update, msg)
                    msg = ''
                msg += addition
    reply_to_message(update, msg)


def help_handler(update, _):
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
    if update.message.from_user.id == MASTER_ID:
        text += "\n\n`/add_global /roll 1d20` \\- add new global roll\n`/remove_global /roll` \\- remove global roll\n"
    reply_to_message(update, text, is_markdown=True)


def add_command_handler(update, _):
    user_id = update.message.from_user.id
    if user_id not in pending_rolls:
        pending_rolls.append(user_id)
    reply_to_message(update, "Ok, now send me command and what it will stands for\\. For example: `/2d6_1 2d6 + 1`",
                     is_markdown=True)


def remove_command_handler(update, context):
    user_id = update.message.from_user.id
    ts = update.message.text.split()
    if len(ts) == 2:
        cmd = ts[1].replace(context.bot.name, '').lstrip('/')
        if len(cmd) > 0:
            custom_roll = db.get_custom_roll(user_id, cmd)
            if custom_roll is not None:
                db.remove_custom_roll(custom_roll)
                reply_to_message(update, "Deleted {} successfully!".format(cmd))
            else:
                reply_to_message(update, "No command named {} found!".format(cmd))
    else:
        reply_to_message(update, "Usage: `/remove your_cmd`", is_markdown=True)


def list_command_handlers(update, _):
    user_id = update.message.from_user.id
    custom_rolls = list(filter(lambda custom_roll: custom_roll.user_id == user_id, db.get_all_custom_rolls()))
    if len(custom_rolls) == 0:
        reply_to_message(update, "You have no custom commands")
    else:
        msg = "Your commands:"
        for custom_roll in custom_rolls:
            msg += "\n/{} - {}d{}".format(custom_roll.shortcut, custom_roll.count, custom_roll.dice)
            if custom_roll.mod_act is not None:
                msg += custom_roll.mod_act + custom_roll.mod_num
        if user_id in pending_rolls:
            msg += "Pending custom command to add"
        reply_to_message(update, msg)


def all_commands_handler(update, context):
    if update.message.text is None or len(update.message.text) == 0 or update.message.text[0] != '/':
        return  # Not a command
    user_id = update.message.from_user.id
    cmd = update.message.text.split()[0][1:].replace(context.bot.name, '').lstrip('/')
    roll = db.get_global_roll(cmd)
    if roll is not None:
        return simple_roll(update, context, roll.count, roll.dice, roll.mod_act, roll.mod_num)
    if user_id in pending_rolls:
        parsed = parse_simple_roll(update.message.text)
        command_text, comment, rolls_cnt, rolls_dice, mod_act, mod_num = parsed
        if ' ' in command_text:
            db.set_custom_roll(CustomRoll(user_id, cmd, rolls_cnt, rolls_dice, mod_act, mod_num))
            pending_rolls.remove(user_id)
            msg = "Added command successfully!\n{} - {}d{}".format(cmd, rolls_cnt, rolls_dice)
            if mod_act is not None:
                msg += mod_act + mod_num
            reply_to_message(update, msg)
        else:
            reply_to_message(update, "Need arguments for command\\. For example: `/2d6_1 2d6+1`", is_markdown=True)
    else:
        custom_roll = db.get_custom_roll(user_id, cmd)
        if custom_roll is not None:
            simple_roll(update, context, custom_roll.count, custom_roll.dice,
                        custom_roll.mod_act, custom_roll.mod_num)


def db_commit(update, _):
    if update.message.from_user.id == MASTER_ID:
        db.commit()
        update.message.reply_text("OK")


# log all errors
def error_handler(update: Update, context: CallbackContext):
    logger.error('Error: {} ({} {}) caused.by {}'.format(context, type(context.error), context.error, update))
    print("Error: " + str(context.error))
    if update.message is not None:
        update.message.reply_text("Error")
        context.bot.send_message(chat_id=MASTER_ID, text="Error: {} {} for message {}".format(
            str(type(context.error))[:1000], str(context.error)[:2000], str(update.message.text)[:1000]))


# start
def init(token):
    # stats loading
    global global_commands

    global_commands = {
        'ping': ping,
        'r': simple_roll,
        '3d6': custom_roll_wrapper(3, 6),
        'c': custom_roll_wrapper(3, 6),
        'c1': custom_roll_wrapper(3, 6),
        'c2': custom_roll_wrapper(3, 6),
        'c3': custom_roll_wrapper(3, 6),
        'c4': custom_roll_wrapper(3, 6),
        'c5': custom_roll_wrapper(3, 6),
        'c6': custom_roll_wrapper(3, 6),
        's': custom_roll_wrapper(1, 11),
        'p': custom_roll_wrapper(1, 100),
        'd': equation_roll,
        'stats': get_stats,
        'statsall': get_full_stats,
        'help': help_handler,
        'add': add_command_handler,
        'remove': remove_command_handler,
        'list': list_command_handlers,
        'commit': db_commit,
        'add_global': add_global_command,
        'remove_global': remove_global_command,
        'get_globals': get_global_commands,
    }

    updater = Updater(token=token, use_context=True)
    # adding handlers
    for command, func in global_commands.items():
        updater.dispatcher.add_handler(CommandHandler(command, func))
    updater.dispatcher.add_handler(MessageHandler(Filters.text, all_commands_handler))
    updater.dispatcher.add_error_handler(error_handler)

    updater.start_polling()
    updater.idle()
    print("Stopping")
    db.close()


if __name__ == '__main__':
    print("Started", time.time())
    init(rollbot_secret_token.token)
