import random
import os


class LocalRandom:
    # get number in [1, max_val] using "true" random
    @staticmethod
    def get_random_num(max_val: int) -> int:
        bin_len = len(bin(max_val)) - 2
        num_cnt, mask = bin_len // 8, (1 << (bin_len % 8)) - 1
        for _ in range(1000):  # 1k tries for "true" cryptographic random
            nums = list(os.urandom(num_cnt + 1))
            nums[0] &= mask
            n = 0
            for i in nums:
                n = (n << 8) + i
            if n != 0 and n <= max_val:
                return n
        # fallback - use default python random
        return random.randrange(max_val) + 1
