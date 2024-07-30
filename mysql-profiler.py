import time
import mysql.connector
from datetime import datetime
from colorama import Fore, Style

def connect_to_database():
    db_config = {
        'user': 'root',
        'password': 'sql2016.',
        'host': 'localhost',
        'database': 'exphadis'
    }    
    return mysql.connector.connect(**db_config)

def fetch_general_log(user_host_filter, latest_event_time):
    connection = connect_to_database()
    cursor = connection.cursor()

    try:
        query = """
            WITH general_log_filtered AS (
                SELECT event_time, user_host, thread_id, command_type, CONVERT(argument USING utf8) as argument
                FROM mysql.general_log
                WHERE user_host LIKE %s 
                    AND command_type = 'Query'
                    AND CONVERT(argument USING utf8) NOT LIKE '%utf8mb4%'
                    AND CONVERT(argument USING utf8) NOT LIKE '%transaction%'
                    AND CONVERT(argument USING utf8) NOT LIKE '%SAVEPOINT%'
                    AND CONVERT(argument USING utf8) NOT LIKE '%commit%'
                    AND CONVERT(argument USING utf8) NOT LIKE '%information_schema.routines%'
                ORDER BY event_time DESC
                LIMIT 1000
            )
            SELECT event_time, argument
            FROM general_log_filtered
            ORDER BY event_time ASC;
        """
        
        cursor.execute(query, (user_host_filter,))

        rows = cursor.fetchall()
            
        new_latest_event_time = latest_event_time

        for row in rows:
            event_time = row[0]
            
            if isinstance(event_time, str):
                event_time = datetime.strptime(event_time, '%Y-%m-%d %H:%M:%S.%f')
                
            argument = row[1]

            if event_time > latest_event_time:
                print(f"{Style.BRIGHT}{Fore.RED}{event_time}{Style.RESET_ALL}:\n{argument}\n")

                if new_latest_event_time is None or event_time > new_latest_event_time:
                    new_latest_event_time = event_time

        return new_latest_event_time

    finally:
        cursor.close()
        connection.close()

def main():
    user_host_filter = '%wgutierrez%'
    latest_event_time = datetime.now()

    try:
        while True:
            latest_event_time = fetch_general_log(
                user_host_filter, 
                latest_event_time) or latest_event_time
            
            time.sleep(1)
    except mysql.connector.Error as err:
        print(f"MySQL Connection Error: {err}")
    except KeyboardInterrupt:
        print("Stopping the monitoring")

if __name__ == "__main__":
    main()
