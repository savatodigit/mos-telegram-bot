import sqlite3
from typing import Optional, List, Dict
from datetime import datetime

class LabTestsDB:
    def __init__(self, db_path: str = "lab_tests.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._create_tables()
        self._import_students()
    
    def _create_tables(self):
        cursor = self.conn.cursor()
        
        # Таблица курсантов с результатами по 12 лабораторным работам
        # Структура: id(0), surname(1), variant(2), created_at(3), 
        #            lr_1(4), lr_2(5), lr_7(6), lr_8(7), lr_9(8), lr_10(9),
        #            lr_11(10), lr_12(11), lr_13(12), lr_14(13), lr_15(14), lr_17(15),
        #            lr_1_date(16), lr_2_date(17), lr_7_date(18), lr_8_date(19),
        #            lr_9_date(20), lr_10_date(21), lr_11_date(22), lr_12_date(23),
        #            lr_13_date(24), lr_14_date(25), lr_15_date(26), lr_17_date(27)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS students (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                surname TEXT NOT NULL,
                variant INTEGER NOT NULL UNIQUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                lr_1 INTEGER DEFAULT 0,
                lr_2 INTEGER DEFAULT 0,
                lr_7 INTEGER DEFAULT 0,
                lr_8 INTEGER DEFAULT 0,
                lr_9 INTEGER DEFAULT 0,
                lr_10 INTEGER DEFAULT 0,
                lr_11 INTEGER DEFAULT 0,
                lr_12 INTEGER DEFAULT 0,
                lr_13 INTEGER DEFAULT 0,
                lr_14 INTEGER DEFAULT 0,
                lr_15 INTEGER DEFAULT 0,
                lr_17 INTEGER DEFAULT 0,
                lr_1_date TIMESTAMP,
                lr_2_date TIMESTAMP,
                lr_7_date TIMESTAMP,
                lr_8_date TIMESTAMP,
                lr_9_date TIMESTAMP,
                lr_10_date TIMESTAMP,
                lr_11_date TIMESTAMP,
                lr_12_date TIMESTAMP,
                lr_13_date TIMESTAMP,
                lr_14_date TIMESTAMP,
                lr_15_date TIMESTAMP,
                lr_17_date TIMESTAMP
            )
        ''')
        
        # Таблица попыток прохождения тестов (история)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_attempts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_id INTEGER NOT NULL,
                variant INTEGER NOT NULL,
                lab_number INTEGER NOT NULL,
                questions_count INTEGER NOT NULL,
                correct_count INTEGER NOT NULL,
                passed BOOLEAN NOT NULL,
                attempted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (student_id) REFERENCES students(id)
            )
        ''')
        
        # Таблица настроек тестирования (включено/выключено преподавателем)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS test_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                tests_enabled BOOLEAN DEFAULT 0,
                enabled_by INTEGER,
                enabled_at TIMESTAMP,
                disabled_by INTEGER,
                disabled_at TIMESTAMP
            )
        ''')
        
        # Инициализация настроек (по умолчанию тесты отключены)
        cursor.execute('''
            INSERT OR IGNORE INTO test_settings (id, tests_enabled) VALUES (1, 0)
        ''')
        
        self.conn.commit()
    
    def _import_students(self):
        """Импортирует студентов из students.txt при первом запуске"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM students")
        count = cursor.fetchone()[0]
        
        if count == 0:
            try:
                with open("students.txt", "r", encoding="utf-8") as f:
                    lines = [l.strip() for l in f if l.strip()]
                
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 2:
                        surname = parts[0].strip()
                        try:
                            variant = int(parts[1])
                            cursor.execute(
                                "INSERT OR IGNORE INTO students (surname, variant) VALUES (?, ?)",
                                (surname, variant)
                            )
                        except ValueError:
                            continue
                
                self.conn.commit()
                print(f"✅ Загружено {len(lines)} курсантов в базу тестов")
            except FileNotFoundError:
                print("⚠️ Файл students.txt не найден")
    
    # ==================== МЕТОДЫ УПРАВЛЕНИЯ ТЕСТАМИ ====================
    def is_tests_enabled(self) -> bool:
        """Проверяет, разрешено ли тестирование"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT tests_enabled FROM test_settings WHERE id = 1")
        row = cursor.fetchone()
        return row[0] == 1 if row else False
    
    def enable_tests(self, admin_id: int):
        """Включает тестирование"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE test_settings 
            SET tests_enabled = 1, enabled_by = ?, enabled_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (admin_id,))
        self.conn.commit()
    
    def disable_tests(self, admin_id: int):
        """Выключает тестирование"""
        cursor = self.conn.cursor()
        cursor.execute('''
            UPDATE test_settings 
            SET tests_enabled = 0, disabled_by = ?, disabled_at = CURRENT_TIMESTAMP
            WHERE id = 1
        ''', (admin_id,))
        self.conn.commit()
    
    def get_test_status(self) -> Dict:
        """Получает текущий статус тестирования"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT tests_enabled, enabled_by, enabled_at, disabled_by, disabled_at 
            FROM test_settings WHERE id = 1
        ''')
        row = cursor.fetchone()
        return {
            "enabled": row[0] == 1 if row else False,
            "enabled_by": row[1],
            "enabled_at": row[2],
            "disabled_by": row[3],
            "disabled_at": row[4]
        }
    
    # ==================== МЕТОДЫ РАБОТЫ С СТУДЕНТАМИ ====================
    def get_student_by_variant(self, variant: int) -> Optional[Dict]:
        """Находит курсанта по варианту"""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, surname, variant FROM students WHERE variant = ?",
            (variant,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return {"id": row[0], "surname": row[1], "variant": row[2]}
    
    def get_student_results(self, student_id: int) -> Optional[Dict]:
        """Получает все результаты курсанта"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM students WHERE id = ?", (student_id,))
        row = cursor.fetchone()
        if not row:
            return None
        
        # ✅ ИСПРАВЛЕНО: результаты начинаются с индекса 4 (после id, surname, variant, created_at)
        lab_numbers = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17]
        results = {}
        dates = {}
        
        for i, lr_num in enumerate(lab_numbers):
            results[f"lr_{lr_num}"] = row[4 + i]  # ✅ БЫЛО: row[3 + i]
            dates[f"lr_{lr_num}_date"] = row[16 + i]  # ✅ БЫЛО: row[15 + i]
        
        return {
            "id": row[0],
            "surname": row[1],
            "variant": row[2],
            "results": results,
            "dates": dates
        }
    
    def update_test_result(self, student_id: int, lab_number: int, passed: bool):
        """Обновляет результат теста для курсанта"""
        # Валидация номера лабораторной работы
        VALID_LAB_NUMBERS = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17]
        
        if lab_number not in VALID_LAB_NUMBERS:
            raise ValueError(f"Недопустимый номер лабораторной работы: {lab_number}")
        
        lab_number = int(lab_number)
        
        cursor = self.conn.cursor()
        cursor.execute(
            f"""UPDATE students 
                SET lr_{lab_number} = ?, lr_{lab_number}_date = CURRENT_TIMESTAMP 
                WHERE id = ?""",
            (1 if passed else 0, student_id)
        )
        self.conn.commit()
    
    def log_attempt(self, student_id: int, variant: int, lab_number: int, 
                    questions_count: int, correct_count: int, passed: bool):
        """Записывает попытку прохождения теста в историю"""
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO test_attempts 
               (student_id, variant, lab_number, questions_count, correct_count, passed) 
               VALUES (?, ?, ?, ?, ?, ?)""",
            (student_id, variant, lab_number, questions_count, correct_count, passed)
        )
        self.conn.commit()
    
    def get_all_results(self) -> List[Dict]:
        """Получает результаты всех курсантов (для админа)"""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM students ORDER BY variant ASC")
        rows = cursor.fetchall()
        
        lab_numbers = [1, 2, 7, 8, 9, 10, 11, 12, 13, 14, 15, 17]
        results = []
        
        for row in rows:
            student_results = {
                "surname": row[1],  # surname на индексе 1
                "variant": row[2]   # variant на индексе 2
            }
            for i, lr_num in enumerate(lab_numbers):
                # ✅ ИСПРАВЛЕНО: результаты начинаются с индекса 4
                student_results[f"lr_{lr_num}"] = row[4 + i]  # ✅ БЫЛО: row[3 + i]
            results.append(student_results)
        
        return results
    
    def close(self):
        self.conn.close()