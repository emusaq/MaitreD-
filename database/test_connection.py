# test_connection.py

from database.connection import connect

def test_db_connection():
    try:
        conn = connect()
        cursor = conn.cursor()
        cursor.execute("SELECT 1;")
        result = cursor.fetchone()
        print("Connection successful. Result:", result)
    except Exception as e:
        print("Connection failed:", e)
    finally:
        if conn is not None:
            conn.close()

if __name__ == "__main__":
    test_db_connection()