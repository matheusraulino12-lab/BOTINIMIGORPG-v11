import random
import re

def roll_damage(dice_expression: str) -> int:
    match = re.match(r"(\d+)d(\d+)\+?(\d+)?", dice_expression)
    if not match:
        return 0

    num, sides, extra = match.groups()
    num = int(num)
    sides = int(sides)
    extra = int(extra) if extra else 0

    return sum(random.randint(1, sides) for _ in range(num)) + extra
