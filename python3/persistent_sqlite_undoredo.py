import sqlite3


DB = None

FIRSTLOG = 1


def connect():
    global DB
    assert DB is None
    print('-- connect')
    DB = sqlite3.connect('test.db')
    DB.isolation_level = None


def close():
    global DB
    assert DB is not None
    print('-- close')
    DB.close()
    DB = None


def list_tables():
    print(DB.execute("SELECT name FROM sqlite_master WHERE type='table';").fetchall())


def enable_undoredo(table):
    collist = DB.execute(f"pragma table_info({table})").fetchall()
    sql = f"CREATE TRIGGER _{table}_it AFTER INSERT ON {table} BEGIN\n"
    sql += "  INSERT INTO undolog VALUES(NULL,"
    sql += f"'DELETE FROM {table} WHERE rowid='||new.rowid);\nEND;\n"

    sql += f"CREATE TRIGGER _{table}_ut AFTER UPDATE ON {table} BEGIN\n"
    sql += "  INSERT INTO undolog VALUES(NULL,"
    sql += f"'UPDATE {table} "
    sep = "SET "
    for (x1, name, x2, x3, x4, x5) in collist:
        sql += f"{sep}{name}='||quote(old.{name})||'"
        sep = ","
    sql += " WHERE rowid='||old.rowid);\nEND;\n"

    sql += f"CREATE TRIGGER _{table}_dt BEFORE DELETE ON {table} BEGIN\n"
    sql += "  INSERT INTO undolog VALUES(NULL,"
    sql += f"'INSERT INTO {table}(rowid"
    for (x1, name, x2, x3, x4, x5) in collist:
        sql += f",{name}"
    sql += ") VALUES('||old.rowid||'"
    for (x1, name, x2, x3, x4, x5) in collist:
        sql += f",'||quote(old.{name})||'"
    sql += ")');\nEND;\n"

    DB.executescript(sql)

    _start_interval()


def _start_interval():
    global FIRSTLOG
    FIRSTLOG = DB.execute(
        "SELECT coalesce(max(seq),0)+1 FROM undolog").fetchone()[0]


def barrier():
    print('-- barrier')
    end = DB.execute("SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]
    begin = FIRSTLOG
    _start_interval()
    if begin == FIRSTLOG:
        return
    DB.execute("INSERT INTO undostack VALUES(?,?)", (begin, end))
    DB.execute("DELETE FROM redostack")


def _step(left_table, right_table):
    global FIRSTLOG
    rowid, begin, end = DB.execute(f"SELECT rowid, begin, end FROM {left_table} ORDER BY rowid DESC LIMIT 1").fetchone()
    DB.execute(f"DELETE FROM {left_table} WHERE rowid=?", (rowid,))
    DB.execute('BEGIN')
    q1 = f"SELECT sql FROM undolog WHERE seq>={begin} AND seq<={end}" \
         " ORDER BY seq DESC"
    sqllist = DB.execute(q1).fetchall()
    DB.execute(f"DELETE FROM undolog WHERE seq>={begin} AND seq<={end}")
    FIRSTLOG = DB.execute(
        "SELECT coalesce(max(seq),0)+1 FROM undolog").fetchone()[0]
    for (sql,) in sqllist:
        DB.execute(sql)
    DB.execute('COMMIT')

    end = DB.execute("SELECT coalesce(max(seq),0) FROM undolog").fetchone()[0]
    begin = FIRSTLOG
    DB.execute(f"INSERT INTO {right_table} VALUES(?, ?)", (begin, end))
    _start_interval()


def undo():
    print('-- undo')
    _step('undostack', 'redostack')


def redo():
    print('-- redo')
    _step('redostack', 'undostack')


def print_world():
    print('firstlog:', FIRSTLOG)
    print('undolog:', DB.execute("SELECT * FROM undolog").fetchall())
    print('undostack:', DB.execute("SELECT * FROM undostack").fetchall())
    print('redostack:', DB.execute("SELECT * FROM redostack").fetchall())
    print('time_slots:', DB.execute("SELECT * FROM time_slot").fetchall())


def main():
    connect()

    DB.execute("CREATE TABLE undolog(seq integer primary key, sql text)")
    DB.execute("CREATE TABLE undostack(begin integer, end integer)")
    DB.execute("CREATE TABLE redostack(begin integer, end integer)")

    DB.execute("CREATE TABLE time_slot(day, start, duration)")
    enable_undoredo('time_slot')

    DB.execute("INSERT INTO time_slot VALUES(?,?,?)", (42, 8, 7))
    barrier()
    print_world()

    DB.execute("INSERT INTO time_slot VALUES(?,?,?)", (23, 9, 8))
    barrier()
    print_world()

    DB.execute("UPDATE time_slot SET start=?,duration=? WHERE day=?", (13, 5, 42))
    barrier()
    print_world()

    undo()
    print_world()

    close()

    connect()

    undo()
    print_world()

    undo()
    print_world()

    redo()
    print_world()

    redo()
    print_world()

    close()


if __name__ == '__main__':
    main()
