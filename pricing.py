"""
Расчёт стоимости проживания по датам на основе сезонной price-таблицы.

Правило: если бронирование пересекается хотя бы одной ночью с пиковым
периодом (1 декабря - 31 января) и короче 30 ночей - вся бронь считается
по полным месячным ценам периодов, которые она затрагивает (не по ночной ставке).
В остальных случаях - обычный посуточный расчёт по периодам.
"""
from datetime import date, timedelta
import calendar

# (label, start_month, start_day, end_month, end_day) - без привязки к году
PERIOD_RANGES = [
    ("Январь", 1, 1, 1, 31),
    ("Февраль", 2, 1, 2, 29),  # 29 покрывает и високосные годы
    ("Март", 3, 1, 3, 31),
    ("Апрель", 4, 1, 4, 30),
    ("Май", 5, 1, 5, 31),
    ("Июнь–Август", 6, 1, 8, 31),
    ("Сентябрь", 9, 1, 9, 30),
    ("Октябрь", 10, 1, 10, 31),
    ("Ноябрь", 11, 1, 11, 30),
    ("1–15 декабря", 12, 1, 12, 15),
    ("15–31 декабря", 12, 16, 12, 31),
]


def get_period_for_date(d: date) -> str:
    month, day = d.month, d.day
    for label, sm, sd, em, ed in PERIOD_RANGES:
        if sm == em:
            if month == sm and sd <= day <= ed:
                return label
        else:
            # диапазон внутри одного календарного отрезка (не пересекает год)
            if (month == sm and day >= sd) or (sm < month < em) or (month == em and day <= ed):
                return label
    return "Февраль" if month == 2 else "Неизвестный период"


def is_peak_date(d: date) -> bool:
    return d.month in (12, 1)


class DateRangeError(Exception):
    pass


def calculate_stay_price(check_in: date, check_out: date, prices: list[dict]) -> dict:
    """
    check_in/check_out - даты заезда/выезда (выезд не включается в число ночей).
    prices - список из 11 периодов [{"period":..., "price_month_thb":..., "price_night_thb":...}, ...]
    """
    nights = (check_out - check_in).days
    if nights <= 0:
        raise DateRangeError("Дата выезда должна быть позже даты заезда")
    if nights > 400:
        raise DateRangeError("Слишком большой период")

    price_by_period = {p["period"]: p for p in prices}
    all_days = [check_in + timedelta(days=i) for i in range(nights)]

    peak_overlap = any(is_peak_date(d) for d in all_days)

    if peak_overlap and nights < 30:
        touched_periods = []
        for d in all_days:
            label = get_period_for_date(d)
            if label not in touched_periods:
                touched_periods.append(label)
        total = 0
        breakdown = []
        for label in touched_periods:
            pinfo = price_by_period.get(label)
            if not pinfo:
                continue
            amount = pinfo["price_month_thb"]
            total += amount
            breakdown.append({
                "period": label,
                "nights": None,
                "rate": None,
                "amount": amount,
                "note": "полная месячная цена (правило дек.-янв., бронь < 30 ночей)",
            })
        return {
            "nights": nights,
            "total_thb": total,
            "breakdown": breakdown,
            "peak_rule_applied": True,
        }

    # обычный посуточный расчёт
    period_nights: dict[str, int] = {}
    for d in all_days:
        label = get_period_for_date(d)
        period_nights[label] = period_nights.get(label, 0) + 1

    total = 0
    breakdown = []
    # сохраняем порядок появления периодов по датам
    seen = []
    for d in all_days:
        label = get_period_for_date(d)
        if label not in seen:
            seen.append(label)

    for label in seen:
        n = period_nights[label]
        pinfo = price_by_period.get(label)
        rate = pinfo["price_night_thb"] if pinfo else 0
        amount = rate * n
        total += amount
        breakdown.append({
            "period": label,
            "nights": n,
            "rate": rate,
            "amount": amount,
            "note": None,
        })

    return {
        "nights": nights,
        "total_thb": total,
        "breakdown": breakdown,
        "peak_rule_applied": False,
    }
