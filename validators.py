import re

def validate_latitude(coord_str: str):
    """Валидация широты: 00°00.0' N/S"""
    pattern = r'^(\d{1,2})°(\d{1,2}(?:\.\d)?)\'\s*([NS])$'
    match = re.fullmatch(pattern, coord_str.strip(), re.IGNORECASE)
    if not match:
        return False, "Неверный формат. Пример: 59°56.0' N"
    
    deg, minutes, direction = match.groups()
    deg, minutes = int(deg), float(minutes)
    
    if not (0 <= deg <= 90):
        return False, "Градусы широты должны быть от 0 до 90"
    if not (0 <= minutes < 60):
        return False, "Минуты должны быть от 0.0 до 59.9"
    if deg == 90 and minutes > 0:
        return False, "На 90° широты минуты должны быть 0.0"
    
    return True, (deg, minutes, direction.upper())

def validate_longitude(coord_str: str):
    """Валидация долготы: 000°00.0' E/W"""
    pattern = r'^(\d{1,3})°(\d{1,2}(?:\.\d)?)\'\s*([EW])$'
    match = re.fullmatch(pattern, coord_str.strip(), re.IGNORECASE)
    if not match:
        return False, "Неверный формат. Пример: 030°15.5' E"
    
    deg, minutes, direction = match.groups()
    deg, minutes = int(deg), float(minutes)
    
    if not (0 <= deg <= 180):
        return False, "Градусы долготы должны быть от 0 до 180"
    if not (0 <= minutes < 60):
        return False, "Минуты должны быть от 0.0 до 59.9"
    if deg == 180 and minutes > 0:
        return False, "На 180° долготы минуты должны быть 0.0"
    
    return True, (deg, minutes, direction.upper())