from db.database import Database, RandomModeTypes
from rnd.LocalRandom import LocalRandom
from rnd.RemoteRandom import RemoteRandom


class Random:
    def __init__(self, db: Database):
        self.db = db
        self.local = LocalRandom()
        self.remote = RemoteRandom()

    # get number in [1, max_val] using "true" random
    def get_random_num(self, max_val: int, source_type: RandomModeTypes = RandomModeTypes.MODE_HYBRID) -> int:
        mode = source_type
        if source_type == RandomModeTypes.MODE_HYBRID:
            if max_val == 6 or max_val == 20:
                mode = RandomModeTypes.MODE_REMOTE
            else:
                mode = RandomModeTypes.MODE_LOCAL
        if mode == RandomModeTypes.MODE_REMOTE:
            rnd = self.remote.get_random_num(max_val)
            if rnd:
                return rnd
        return self.local.get_random_num(max_val)

    # returns an integer from 1 to dice inclusively and add result to stats
    def random(self, dice: int, chat_id: int = -1) -> int:
        dice = abs(dice)  # remove negative values
        if dice == 0 or dice > 1000000:
            dice = 20  # remove incorrect
        mode = RandomModeTypes.MODE_HYBRID
        if chat_id != -1:
            settings = self.db.get_chat_settings(chat_id)
            if settings:
                mode = RandomModeTypes(settings.random_mode)
        res = self.get_random_num(dice, mode)
        self.db.increment_stat(dice, res)
        return res
