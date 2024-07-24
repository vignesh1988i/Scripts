#
# Wrapping Module for PostGres DB packages
# Author: vignesh.sundararaman
#
import os,sys
import os.path
import psycopg2
import json
import time

from configparser import ConfigParser

#
# The DB_CONFIG can be changed based on your Firm wide Data paths
#
DB_CONFIG='/data/mqm/DBA/etc/.db.ini'
DEBUG=False
ENV=['DEV','QA','PROD']

""" Custom Exception Handling """
class ValuenotInteger(Exception):
    """ Raise this Exception if Passed value not an Integer """
    def __init__ (self, value, message='Value not an INT'):
        self.value = value
        self.message = message
        super().__init__(self.message)


class DB:

    def __init__(self, env, config=DB_CONFIG, debug=False):
        self.__conn = None
        self.__cursor = None

        if env not in ENV:
            raise Exception('Environment is invalid - %s' % (env))

        if (debug):
            global DEBUG
            DEBUG=True

        if (os.path.isfile(config)):
            self.__config = config
            self.__db_params = self.__dbconfig(env)
        else:
            raise Exception('The config doesn''t exists - [{0}]'.format(config))
                

    def __dbconfig(self, env, section='postgresql'):
        # create a parser
        parser = ConfigParser()
        # read config file
        parser.read(self.__config)

        # get section, default to postgresql
        db = {}
        section = section + "_" + env 
        if parser.has_section(section):
            params = parser.items(section)
            for param in params:
                db[param[0]] = param[1]
        else:
            raise Exception('Section {0} not found in the {1} file'.format(section, filename))

        return db


    def Connect(self):
        """ Connect to the PostgreSQL database server """
        if (self.__conn is not None):
            raise Exception('You already have a DB Connection Established, DB Connection Header - [{0}]'.format(self.__conn))
        
        if (not self.__config):
            raise Exception('Not valid config to pass for the DB Connection')
 
        if (DEBUG): print('Connecting to the PostgreSQL database...') 
        try:
            self.__conn = psycopg2.connect(**self.__db_params)
            return self.__conn 
        except (Exception, psycopg2.DatabaseError) as error:
            raise Exception('DB Connection Exception happened - [{0}]'.format(error))
        

    def Cursor(self):
        """ Get the cursor point for Database fetch """
        if (self.__conn is None):
            raise Exception('You dont have a valid DB Connection to get a cursor')

        self.__cursor = self.__conn.cursor()
        return self.__cursor

    def CurrentCursor(self):
        """ Get Current Cursor """
        if (self.__cursor):
            return self.__cursor
            

    def Execute(self, query,  max_retries=3, retry_wait=10):
        """ Execute the given query. Commit/Rollback based on execution """

        if (self.__conn is None):
            raise Exception('You dont have a valid DB Connection to execute the query')

        if (self.__cursor is None):
            self.dbclose()
            raise Exception('You dont have a valid cursor defined to execute this query')

        if (not type(max_retries) is int):
            self.__grace_close()
            raise ValuenotInteger(max_retries, "max_retries should be INT , but given [{0}]".format(type(max_retries))) 

        if (not type(retry_wait) is int):
            self.__grace_close()
            raise ValuenotInteger(retry_wait, "retry_wait should be INT , but given [{0}]".format(type(retry_wait)))

        for _ in range(max_retries):
            try: 
                self.RowCount = 0
                self.__cursor.execute(query)
                #print (self.__cursor.rowcount)

            except psycopg2.Error as e:
                """ Reference : https://www.psycopg.org/docs/module.html#psycopg2.Error """
                print ("Error while processing the query - [%s]" % query)
                print ("PG Code - %s, PG Error - %s" % (e.pgcoe, e.pgerror))
                self.Rollback()
                print ("Retrying in sometime")
                time.sleep(retry_wait)
                continue
            else:
                #if (bool(not self.Fetchone())):
                #    raise Exception("Table doesn't exists")

                self.RowCount = self.__cursor.rowcount
                self.Commit()
                return 

        print ("Couldn't Process the query even after retrying!!! Skipping it")


    def Rowcount(self): 
        if (self.__conn):
            if (self.__cursor):
                return int(self.RowCount)

 
    def Fetchone(self):
        if (self.__conn):
            if (self.__cursor):
                return self.__cursor.fetchone()

    def Fetchall(self):
        if (self.__conn):
            if (self.__cursor):
                return self.__cursor.fetchall()

    def curDescription(self):
        if (self.__conn):
            if (self.__cursor):
                return self.__cursor.description

    def Rollback(self):
        """ roll back the transaction """
        if (self.__conn):
            if (self.__cursor):
                self.__conn.rollback()
                return

        raise Exception('Invalid rollback call')
        self.__grace_close()


    def Commit(self):
        """ Commits the transaction """
        if (self.__conn):
            if (self.__cursor):
                self.__conn.commit()
                return
            
        raise Exception('Invalid Commit call')  
        self.__grace_close()


    def __grace_close(self):
        """ Close the DB Connection if there are any mid way exception """
        self.cursor_close()
        self.dbclose()

    def DBVersion(self):
        """ display the PostgreSQL database server version """
        if (self.__conn is None):
            self.Connect()
            self.Cursor()
        elif (self.__cursor is None):
              self.Cursor()

        if (DEBUG): print('PostgreSQL database version:')
        self.Execute("SELECT version()")
        db_version = self.__cursor.fetchall()
        self.cursor_close()
        self.dbclose()
        return db_version[0][0] # List of Tuple converted to string

            
    def DBListTables(self):
        """ display the PostgreSQL database table names that are Public """
        if (self.__conn is None):
            self.Connect()
            self.Cursor()
        elif (self._cursor is None):
            self.Cursor()

        if (DEBUG): print('Listing PostgreSQL database Table Names marked "Public" :')
        self.Execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = []
        for table in self.__cursor.fetchall():
            tables.append(table[0])

        self.cursor_close()
        self.dbclose()
        if (tables):
            return tables # list 


    def cursor_close(self):
        if (self.__conn):
            if (self.__cursor):
                #self.Rowcount=0
                self.__cursor.close()
            self.__cursor=None


    def dbclose(self):
        if (self.__conn):
            if (self.__cursor):
                #self.Rowcount=0
                self.__cursor.close()

            self.__conn.close()
            self.__cursor=None
            self.__conn=None
