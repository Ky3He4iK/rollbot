from datetime import datetime
import math
from typing import Optional
import asyncio

import aiohttp


class RemoteRandom:
    def __init__(self):
        self.storage = {}
        # self.mutex = Lock()
        self.data = {20: [], 6: []}
        self.data_queue = {}
        self.is_working = True
        self.remote_random = True

        self.quota_left = 200_000
        self.quota_date = datetime.now().day

        self.loop = asyncio.get_event_loop()
        self.loop.run_until_complete(self.run_thread())

    def get_random_num(self, dice: int) -> Optional[int]:
        def get_data() -> Optional[int]:
            if dice in self.data:
                items = self.data[dice]
                if len(items) >= 1:
                    item = self.data[dice].pop()
                    return item
            return None

        if dice in self.data_queue:
            self.data_queue[dice] += 1
        else:
            self.data_queue[dice] = 1

        loop = asyncio.get_event_loop()
        while True:
            loop.run_until_complete(asyncio.sleep(0.2))
            res = get_data()
            if res is not None:
                return res
            if not self.remote_random:
                return None

    def stop(self):
        self.is_working = False

    async def run_thread(self):
        async def fetch_numbers(count: int = 1e4) -> bool:
            try:
                est_quota = math.log2(dice) * 1.9 * count
                if est_quota < self.quota_left:
                    self.quota_left -= est_quota
                    nums_raw = await fetch(f'integers/?num={count}&min=1&max={dice}&col=1&base=10&format=plain&rnd=new')
                    nums = list(map(int, nums_raw.splitlines()))
                    self.data[dice] = nums + self.data[dice]
                    return True
                else:
                    self.remote_random = False
            except BaseException as ex:
                print(ex)
            return False

        async def fetch(url, base_url='https://www.random.org/') -> str:
            async with session.get(base_url + url,
                                   headers={'User-Agent': 'Telegram rollbot misha10311@yandex.ru'}) as response:
                return await response.text()

        async with aiohttp.ClientSession() as session:
            # try:
            #     quota = await fetch('quota/?format=plain')
            #     quota = int(quota)
            #     if quota < self.quota_left:
            #         self.quota_left = quota * 8 // 10
            # except BaseException as e:
            #     print(e)
            while self.is_working:
                # update quota
                now = datetime.utcnow()
                if now.day != self.quota_date and now.hour > 1:
                    self.quota_left += 200_000
                    self.quota_date = now.day
                    self.remote_random = True

                # process requests
                for dice, left in self.data_queue.items():
                    while left > 8000:
                        if not await fetch_numbers(10000):
                            break
                        left -= 10000
                    if not await fetch_numbers(left + 1000):
                        break
                # fill data
                for dice, left in self.data.items():
                    if len(left) < 10:
                        if not await fetch_numbers():
                            break

                await asyncio.sleep(1)
