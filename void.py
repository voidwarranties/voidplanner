#!/usr/bin/python
#
##################################################################################
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##################################################################################
#
# This script sends out emails to people tied into a list to inform them that
# one of them is supposed to go and do something set into the near future.
# Based on the future schedule everyone is informed of who is next on the list
# for some time to come (several weeks).
# 
# When the person in charge also has his/her mobile/GSM-number available
# in the listing it's possible to drop them an SMS 24 or less in advance.
# Please see.... for more details
#

import sys, os

from smtplib import SMTP
from email.mime.text import MIMEText

from datetime import date,datetime,timedelta

from string import Template

import locale

from pytz import timezone
from pytz import utc
from pytz.exceptions import UnknownTimeZoneError

import argparse

##################################################################################
#
# Config
#
##################################################################################
#The general message heading in the email to be sent 
templateActivity = 'Wie doet de space open aanstaande woensdag?'

#Message to be sent in case there are no candidates this week 
templateNoActivity = 'Komende week gaat de space mogelijk niet open'
templateBericht = ' doe jij uiterlijk om 20:00 de space open.\n'
templateSmsReminder = 'Vanavond doe jij om 20:00 de space open'

##################################################################################
#
# Parse arguments from the commandline
#
##################################################################################
parser = argparse.ArgumentParser(
	usage='%(prog)s [options]',
	description='Job rotation organiser.',
	formatter_class=argparse.ArgumentDefaultsHelpFormatter,
	epilog='This script helps you to coordinate a regular task taken up '\
		'by a group of people based on a planned set of events. '\
		'The planning is done with a date-segmented table of contributors. '\
		'Communication is supported through email and SMS'
)

parser.add_argument('--filename',
	required=True,
	help='CSV File holding the planned events'
)

parser.add_argument('--templates',
	required=False,
	type=argparse.FileType('r'),
	help='Several template texts in csv-format which will be expanded'
)

parser.add_argument('--smtphost',
	required=True, 
	default='172.0.0.1',
	help='smtp host '
)

parser.add_argument('--smtpport',
	type=int,
	default=587,
	choices=(25,587),
	help="Port 587 (STARTSSL) is supported. Sending over port 25 is not encouraged")

parser.add_argument('--smtpuser',
	help='username to contact smtp server'
)

parser.add_argument('--smtppassword',
	help='password to contact smtp server'
)

parser.add_argument('--sender',
	required=True,
	help='The emailadres of the perceived sending instance'
)

parser.add_argument('--locale', dest='locale_string',
	default="en_US.utf8",
	help='Locale for use in localized date and time.'
)

parser.add_argument('--timezone', dest='tz',
	default=utc.zone,
  help='Timezone for l18n purposes. Example: "Europe/Berlin"'
)

smtpdebug = 0

##################################################################################
#
# The code or the "hard part"
#
##################################################################################

def readPlanning(filename):
	datafile = open(filename, 'r')
	data = []
	for row in datafile:
		try:
			if row.strip().startswith('#'):
				continue
			#reading in CSV-rows
			tuple = row.strip().split(':')
			#skip dates from the past
			date = datetime.strptime(tuple[0],'%Y-%m-%d')
			if (date - date.today()).days >= 0:
				tuple[0] = date #zet de datumstring om in een datumobject
				data.append(tuple)
		except ValueError , e:
			print '"%s" is geen geldig datumveldje...' % tuple[0]
			continue

	#print data
	return data

def readTemplates(templates):
	data = []
	for row in templates:
		try:
			# skip empty lines
			if not ''.join(row).strip():
				continue
			
			# skip comments
			if row.strip().startswith('#'):
				continue

			#reading in CSV-rows (':') is the delimiter
			tuple = row.strip().split(':')

			data.append(tuple)

		except ValueError , e:
			print e

	return data

def pickNearestCandidate(database):
	nearestRecord = None
	pdelta = timedelta.max
	for row in database:
		delta = row[0] - datetime.today()
		if delta.days < pdelta.days :
			pdelta = delta
			nearestRecord = row
	
	#print nearestRecord
	return nearestRecord

def addressplitter(instr):
	print "instr %s" % instr
	return instr.split(',')


#This sets the overal Locale string for the rest of this script
def setLocaleFromString(locale_string):
	try: 
		#print '%s ' % locale_string
		locale.setlocale(locale.LC_TIME, locale_string)

	except locale.Error , e:
		print 'Error: %s' % e
		print ' * Check you spelling or '
		print ' * consider running: dpkg-reconfigure locales'
		sys.exit(-1)

def createLocalizedDate(tz):

	try: 
		#force the output to english
		locale.setlocale(locale.LC_TIME, "en_US.utf8")
		#but use the senders (this machine's) timezone 
		fmt = '%a, %d %b %Y %X %z (%Z)'
		localdate = timezone(tz).localize(datetime.today()).strftime(fmt) 

		return localdate

	except UnknownTimeZoneError, e:
		print '%s' % e

# Dump file to transfer to smsgateway.
# Transfering the file is left to another script in case you don't have 
# an sms gateway (smsdtools) installed locally
#
def dumpSmsFileForTransfer(gsm, text, senddate):
	#If senddate is not set, make it today.
	#Make sure your sms gateway gets the outputfile
	if senddate is '' :
		senddate=datetime.today()
	if gsm is '' :
		print "No GSM number found. Can't send SMS"
		return
	if text is None :
		print "No text tos send found. Can't send SMS"
		return

	try : 
		pathname = os.path.dirname(sys.argv[0])        
		programm = os.path.splitext(os.path.basename(__file__))[0]
		file = "/var/tmp/%s-%s.txt" % (senddate.strftime('%Y-%m-%d'), programm)
		print "Dumping SMS-file to: %s" % file
		datafile = open(file, 'w')
		datafile.write("To: %s\n" % gsm)
		datafile.write("\n%s\n" % text)
		datafile.close()
	except IndexError, ie :
		print ie
		print "No GSM number found. Can't send SMS"

def buildMessage(sender, candidate, database, template):
	message = ''

	date = candidate[0]
	aan = candidate[1]
	naam = candidate[2]

	#tekst voor het berichtje opbouwen, afhankelijk van of er al dan niet gehaald moet worden
	if naam <> None:
		#s = Template(template)
		#message+= s.substitute(who=naam, date=date.strftime("%A %d %B"))
		message+= 'Hoi %s,\n' %naam
		message+= '\nOp %s' % date.strftime("%A %d %B")
		message+= templateBericht
		message+= 'Kan je onverhoopt niet, ruil dan tijdig met de anderen.'
		message+= '\n'
		#print "To: %s" % aan
		
	#planning invoegen voor de komende weken
	message+= '\nDe verdere planning voor de komende weken ziet er zo uit:'
	for row in database[1:7]:
		message+= '\n* %s\t%s' % (row[0].strftime('%d %B'), row[2])
	
	message+= '\n\n--'
	message+= '\nDit bericht werd U aangeboden door %s in samenwerking met crontab, python (sssss) en een smsgateway.' % sender
	#print message;
	return message

###
# Building a MIME object with a message that will be sent to 
# the one who has it's turn. In CC all the others to make sure
# everyone knows what was communicated.
def sendMail(sender, message, candidate, subject, database):
	#Wrap the contents in MIME object
	msg = MIMEText(message)

	msg['From'] = sender
	msg['Subject'] = subject

	#Add proper timestamp in English but keep locale timezone
	msg['Date'] = createLocalizedDate(args.tz)

	# De To- en CC-headers toevoegen; 'to' met ALLE geadresserden 
	# wordt verderop gebruikt bij het effectief versturen!
	#
	to = candidate[1]
	name = candidate[2]
	cclist = []
	for row in database:
		if row[2] <> name and row[1] not in cclist:
			cclist.append(row[1])

	# In het geval dat er niemand moet gaan halen vervalt de cc-lijst
	# en wordt iedereen direct gemaild via het to-veldje
	if name == None:  
		msg['To'] = ", ".join(map(str, cclist))
		recipients = cclist
	else:
		msg['To'] = to
		msg['Cc'] = ", ".join(map(str, cclist))
		recipients = cclist
		recipients.append(to)

	print msg
	print 'will be sent to....: %s' % recipients

	try:
		s = SMTP(args.smtphost,args.smtpport)
		s.set_debuglevel(smtpdebug)

		if args.smtpport == 587:
			s.starttls()

		if args.smtpuser != None and args.smtppassword != None :
			s.login(args.smtpuser, args.smtppassword)

		#s.sendmail(sender, recipients, msg.as_string())

	except Exception, e:
		print e
	finally:
		s.quit()

	return

args = parser.parse_args()
#parser.print_help()

#The locale used to in strftime operations during execution of this script
setLocaleFromString(args.locale_string)

pathname = os.path.dirname(sys.argv[0])        
#print pathname
database = readPlanning(pathname+"/"+args.filename)

#templates = dict(readTemplates(args.templates))
#print templates

#messageTemplate =  templates['message']
messageTemplate = None

#activity =  templates['activity']
activity =  templateActivity

#noActivity =  templates['noActivity']
noActivity =  templateNoActivity

#signature =  templates['signature']
#smsReminder =  templates['smsReminder']
smsReminder = templateSmsReminder

#sys.exit(-1)

#zoek de eerstvolgende pineut...
candidate = pickNearestCandidate(database)
if candidate is None: 
	#nothing found on the horizon
	print "No valid dates in the future present. Script %s needs to be update with futureentries." % sys.argv[1]
	sys.exit(-1)

devolgende = (candidate[0] - datetime.today()).days
#sys.exit(-1)

#print 'De volgende haaldag is over %d dagen' % devolgende 
#FIXME: this assumes a 7day recurring sequence
if devolgende < 7:
	message = buildMessage(args.sender, candidate, database, messageTemplate)
	#sys.exit(-1)
	sendMail(args.sender, message, candidate, activity, database)
	#dumpSmsFileForTransfer(candidate[3], smsReminder, candidate[0])
else:
	#override de candidate, niemand moet halen, wel iedereen inlichten.
	candidate = (None, None, None)
	message = buildMessage(args.sender, candidate, database)
	sendMail(args.sender, message, candidate, noActivity, database)


