import os
import sqlite3

def check_database(db_name):
    try:
        with sqlite3.connect(db_name) as conn:
            cursor = conn.cursor()

            cursor.execute("""
                    CREATE TABLE IF NOT EXISTS registered_users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        name TEXT,
                        purpose TEXT
                    );
                """)
            print("Таблица 'registered_users' проверена/создана")

            cursor.execute("""
                    CREATE TABLE IF NOT EXISTS decode_flag (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        chat_id INTEGER NOT NULL UNIQUE,
                        flag INTEGER
                    );
                """)
            print("Таблица 'decode_flag' проверена/создана")

            conn.commit()

    except sqlite3.Error as e:
        print(f"Ошибка при работе с базой данных: {e}")


def check_folders(folders):
    for folder in folders:
        if os.path.exists(folder):
            print(f"Папка '{folder}' существует")
        else:
            os.makedirs(folder)
            print(f"Папка '{folder}' была создана")
