import urllib2
import datetime
import string
import sys
import csv
import MySQLdb

prtgIP = "xx.xx.xx.xx"
currenttime = datetime.datetime.now()
sensorlist = []

#Read csv file to create a list of sensor ID need to check

if currenttime.time() >= datetime.time(hour=0) and currenttime.time() <= datetime.time(hour=6):
    with open('sensor-night.csv', 'r') as f:
        csv_reader = csv.reader(f)
        for row in csv_reader:
            sensorlist.append((row[0],row[1],row[2],row[3]))
else:
    with open('sensor-day.csv', 'r') as f:
        csv_reader = csv.reader(f)
        for row in csv_reader:
            sensorlist.append((row[0],row[1],row[2],row[3]))
    
#Read csv file to create a list of email to send notification
emaillist = []
with open('email.csv', 'r') as f:
    csv_reader = csv.reader(f)
    for row in csv_reader:
        emaillist.append(row[0])
#print emaillist

#User and password to connect to PRTG API
username = "API"
password = "APIUser1"

#User, password and details to connect to MySQL database
con = MySQLdb.connect(host='localhost', user='prtg', passwd='prtg', db='sensordata')
cur = con.cursor()

#User, password to send mail
emailuser = "xxxxx@gmail.com"
emailpassword = "xxxxx"

historyscan = 2 # Number of results will be returned from history check

resultmessage = ""
checkresult = 0
checkresulttemp = 0
emailtitle = "PRTG Alert dip check"

#### A small function to check if value of sensor is number or not
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

        
#### Function to send email
def send_email(user, pwd, recipient, subject, body):
    import smtplib
    global sendemailresult

    FROM = user
    TO = recipient if type(recipient) is list else [recipient]
    SUBJECT = subject
    TEXT = body

    # Prepare actual message
    message = """From: %s\nTo: %s\nSubject: %s\n\n%s
    """ % (FROM, ", ".join(TO), SUBJECT, TEXT)
    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)
        server.ehlo()
        server.starttls()
        server.login(user, pwd)
        server.sendmail(FROM, TO, message)
        server.close()
        sendemailresult = 0
    except:
        sendemailresult = 1

########## Function dip check

def dipcheck(prtgIP,sensorID,sensordetail,sensoralias,sensordip,username,password):
    global checkresulttemp
    global delta
    global deltapercentage
    global currentstring
    global lastvaluestring
    
    valuelist = []
    temp = 0
    # Display current value

    url = "http://%s/api/getsensordetails.xml?id=%s&username=%s&password=%s"% (prtgIP,sensorID,username,password)
    s = urllib2.urlopen(url)
    contents = s.read()
    file = open("export1.xml", 'w')
    file.write(contents)
    file.close()

    import xml.etree.ElementTree as ET

    tree = ET.parse('export1.xml')
    current = tree.findtext("lastvalue")

    current = current.strip()
    current = string.replace(current," kbit/s","")
    current = string.replace(current,",","")
    
    #Check if current value is a number or not
    if is_number(current):
        current = float(current)
    else:
        current = 0
    #print current

    ########## End of current value check #######

    #### Scan last value to detect dip (how many value depend of variable 'historyscan'

    query = "SELECT sensorvalue from prtgdata where sensoralias LIKE %s ORDER BY dateandtime DESC LIMIT %s"
    sensoralias1 = "%" + sensoralias
    args=(sensoralias1,historyscan)
    cur.execute(query, args)
    
    for row in cur.fetchall():
        valuelist.append(row[0])
    #print valuelist
    length = len(valuelist)
    ## Check if there is a dip ##
    
    try:
        firstlastvalue = valuelist[length - 2]
    except IndexError:
        firstlastvalue = 0
    try:
        secondlastvalue = valuelist[length - 1]
    except IndexError:
        secondlastvalue = 0

    secondlastvalue = float(secondlastvalue)
    firstlastvalue = float(firstlastvalue)
    current = float(current)
    currentstring = ""
    lastvaluestring =""
    delta = 0
    deltapercentage = 0
    sensordipcheck = (100-float(sensordip))/100
    if sensordipcheck <0 : sensordipcheck = 0
    if (((secondlastvalue *sensordipcheck) - current) > 0) and (((secondlastvalue *sensordipcheck) - firstlastvalue) > 0) :
        #print "1:NOK"
        delta = (secondlastvalue - current)/1000
        delta = round(delta,1)
        deltapercentage = 100*(secondlastvalue - current)/secondlastvalue
        deltapercentage = round(deltapercentage,1)
        currentstring = str(round((current/1000),1))
        lastvaluestring = str(round((secondlastvalue/1000),1))
        checkresulttemp = 1 
    else:
        #print "0:OK"
        checkresulttemp = 0

    #Prepare a debug value, only enable when needed
    debugvalue = str(current) + "," + str(firstlastvalue) + "," + str(secondlastvalue) + "," + str(checkresulttemp)
    #debugvalue = ""
    # Put current sensor value into MySQL Database
    query = "INSERT INTO prtgdata(dateandtime,sensorID,sensorvalue,sensordetail,sensoralias,debugvalue) VALUES(CURRENT_TIME(),%s,%s,%s,%s,%s)"
    args = (sensorID, current, sensordetail,sensoralias,debugvalue)
    cur.execute(query, args)
    con.commit()
    
    #####End of dipcheck function#####

    
    return

###### MAIN Program

for i1 in xrange(len(sensorlist)):
    dipcheck(prtgIP,sensorlist[i1][0],sensorlist[i1][1],sensorlist[i1][2],sensorlist[i1][3],username,password)
    checkresult = checkresult | checkresulttemp
    if checkresulttemp == 1 : resultmessage = resultmessage + sensorlist[i1][1] + " (" + currentstring + "Mbit" + "," + lastvaluestring + "Mbit" + "," + str(delta)+ "Mbit" + "-" + str(deltapercentage) + "%)/\n"

#Prepare message to send when issue found
if (checkresult ==1): msg = str(resultmessage)

#Take last value of the result in database
query = "SELECT dateandtime,checkresult,resultmessage from prtgresult ORDER BY dateandtime DESC LIMIT 1"
cur.execute(query)
for row in cur.fetchall():
    lastdateandtime = row[0]
    lastcheckresult = row[1]
    lastresultmessage = row[2]
    
#Found new issue in traffic, send mail and insert record to email data
if ((lastcheckresult ==0) and (checkresult ==1)) or ((lastcheckresult ==1) and (checkresult ==1) and (lastresultmessage != resultmessage)):
    emailmsg = msg
    currenttime1 = currenttime.strftime("%Y-%m-%d %H:%M:%S")
    emailmsg = "DIP detected:\n\n" + emailmsg + "\n\n" +str(currenttime1)
    send_email(emailuser,emailpassword,emaillist,emailtitle,emailmsg)
    query = "INSERT INTO emaildata(dateandtime,emailtype,emailmessage,sendemailresult) VALUES(CURRENT_TIME(),%s,%s,%s)"
    args = ("DIP detected",msg,sendemailresult)
    cur.execute(query, args)
    con.commit()

#Return to normal, send mail and insert record to email data
#if (lastcheckresult ==1) and (checkresult ==0):
#    emailmsg = "No more dip detected in all traffic"
#    send_email(emailuser,emailpassword,emaillist,emailtitle,emailmsg)
#    query = "INSERT INTO emaildata(dateandtime,emailtype,emailmessage,sendemailresult) VALUES(CURRENT_TIME(),%s,%s,%s)"
#    args = ("Normal","",sendemailresult)
#    cur.execute(query, args)
#    con.commit()

#Take last time when we send email from database
query = "SELECT dateandtime from emaildata ORDER BY dateandtime DESC LIMIT 1"
cur.execute(query)
lastemail = datetime.datetime.now()
for row in cur.fetchall():
    lastemail = row[0]
#print lastemail
    
#If issue exist for 1 hour, send reminder email and insert record to email data
#if (lastcheckresult ==1) and (checkresult ==1) and (abs(datetime.datetime.now() - lastemail) > datetime.timedelta(hours=1)):
#    emailmsg = "REMINDER 1 hour:\n" + msg
#    send_email(emailuser,emailpassword,emaillist,emailtitle,emailmsg)
#    query = "INSERT INTO emaildata(dateandtime,emailtype,emailmessage,sendemailresult) VALUES(CURRENT_TIME(),%s,%s,%s)"
#    args = ("Reminder",msg,sendemailresult)
#    cur.execute(query, args)
#    con.commit()

#If no issue for 2 hour, send Heartbeat email and insert record to email data
if (lastcheckresult ==0) and (checkresult ==0) and (abs(datetime.datetime.now() - lastemail) > datetime.timedelta(hours=2)):
    emailmsg = "HEARTBEAT: No issue detected in last 2 hours"
    send_email(emailuser,emailpassword,emaillist,emailtitle,emailmsg)
    query = "INSERT INTO emaildata(dateandtime,emailtype,emailmessage,sendemailresult) VALUES(CURRENT_TIME(),%s,%s,%s)"
    args = ("Heartbeat","",sendemailresult)
    cur.execute(query, args)
    con.commit()


query = "INSERT INTO prtgresult(dateandtime,checkresult,resultmessage) VALUES(CURRENT_TIME(),%s,%s)"
args = (checkresult,resultmessage)
cur.execute(query, args)
con.commit()

#Delete old data, optimize the database
if currenttime.time() >= datetime.time(hour=10) and currenttime.time() <= datetime.time(hour=10, minute=1):
    query = "DELETE FROM `prtgdata` WHERE dateandtime < date_sub(now(), interval 4320 minute)"
    cur.execute(query)
    con.commit()
    query = "OPTIMIZE TABLE `prtgdata`"
    cur.execute(query)
    con.commit()

if currenttime.time() >= datetime.time(hour=10, minute=13) and currenttime.time() <= datetime.time(hour=10, minute=14):
    query = "DELETE FROM `emaildata` WHERE dateandtime < date_sub(now(), interval 4320 minute)"
    cur.execute(query)
    con.commit()
    query = "OPTIMIZE TABLE `emaildata`"
    cur.execute(query)
    con.commit()

if currenttime.time() >= datetime.time(hour=10, minute=23) and currenttime.time() <= datetime.time(hour=10, minute=24):
    query = "DELETE FROM `prtgresult` WHERE dateandtime < date_sub(now(), interval 4320 minute)"
    cur.execute(query)
    con.commit()
    query = "OPTIMIZE TABLE `prtgresult`"
    cur.execute(query)
    con.commit()

cur.close()
con.close()


#Print the output for PRTG sensor
if (checkresult ==0) : print "0:OK"

if (checkresult ==1) : print "1:NOK"
