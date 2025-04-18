import time
import mysql.connector
from datetime import datetime, timezone, timedelta
from colorama import Fore, Style

# 🌍 Set your local timezone offset here (e.g., -5 for Peru/Lima)
LOCAL_TZ_OFFSET_HOURS = -5

def connect_to_database():
    db_config = {
        'user': 'root',
        'password': 'sql2016.',
        'host': '192.168.18.150',
        'port': 33061,
        'database': 'exphadis'
    }    
    return mysql.connector.connect(**db_config)

def convert_utc_to_local(utc_dt):
    """Converts a UTC datetime to local timezone using the fixed offset"""
    local_tz = timezone(timedelta(hours=LOCAL_TZ_OFFSET_HOURS))
    return utc_dt.replace(tzinfo=timezone.utc).astimezone(local_tz)

def fetch_general_log(user_host_filter, latest_event_time):
    connection = connect_to_database()
    cursor = connection.cursor()

    try:
        local_tz = timezone(timedelta(hours=LOCAL_TZ_OFFSET_HOURS))
    
        query = """
            WITH general_log_filtered AS (
                SELECT 
                    event_time, 
                    user_host, 
                    thread_id, 
                    command_type, 
                    CONVERT(argument USING utf8) as argument
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

        new_latest_event_time = latest_event_time.astimezone(local_tz)

        for row in rows:
            event_time = row[0]
            
            if isinstance(event_time, str):
                event_time = datetime.strptime(event_time, '%Y-%m-%d %H:%M:%S.%f')
            
            # print(f"event_time: {event_time}\n")
            
            event_time = event_time.replace(tzinfo=local_tz)
            
            # print(f"event_time with timezone: {event_time}\n")
            
            # print(f"latest_event_time : {latest_event_time}\n")
            
            # print(f"event_time > latest_event_time : {event_time > latest_event_time}\n")
                
            argument = row[1]

            if event_time > latest_event_time.astimezone(local_tz):
                local_time = convert_utc_to_local(event_time)
                
                print(f"{Style.BRIGHT}{Fore.RED}{local_time}{Style.RESET_ALL}:\n{argument}\n")

                if new_latest_event_time is None or event_time > new_latest_event_time:
                    new_latest_event_time = event_time

        return new_latest_event_time

    finally:
        cursor.close()
        connection.close()

def main():
    user_host_filter = '%wgutierrez%'
    local_tz = timezone(timedelta(hours=LOCAL_TZ_OFFSET_HOURS))
    latest_event_time = datetime.now(local_tz)

    # print(f"latest_event_time in main: {latest_event_time}\n")
            
    try:
        while True:
            latest_event_time = fetch_general_log(user_host_filter, latest_event_time) or latest_event_time
            time.sleep(1)
    except mysql.connector.Error as err:
        print(f"MySQL Connection Error: {err}")
    except KeyboardInterrupt:
        print("Stopping the monitoring")

if __name__ == "__main__":
    main()
