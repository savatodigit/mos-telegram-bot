import os

variants = [f"{i:02d}" for i in range(1, 100)]  # 01-99
lab_numbers = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17]

found = 0
missing = []

for variant in variants:
    for lab in lab_numbers:
        filename = f"files/{variant}-ЛР {lab}.pdf"
        if os.path.exists(filename):
            found += 1
        else:
            missing.append(filename)

print(f"✅ Найдено файлов: {found}")
print(f"❌ Отсутствует файлов: {len(missing)}")

if missing:
    print("\nПримеры отсутствующих файлов (первые 5):")
    for f in missing[:5]:
        print(f"  • {f}")