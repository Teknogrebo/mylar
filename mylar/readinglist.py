
#  This file is part of Mylar.
#
#  Mylar is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  Mylar is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with Mylar.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import with_statement

import os
import re
import mylar

from mylar import logger, db, helpers

class Readinglist(object):

    def __init__(self, filelist=None, IssueID=None, IssueArcID=None):

        if IssueID:
            self.IssueID = IssueID
        else:
            self.IssueID = None
        if IssueArcID:
            self.IssueArcID = IssueArcID
        else:
            self.IssueArcID = None
        if filelist:
            self.filelist = filelist
        else:
            self.filelist = None

        self.module = '[READLIST]'

    def addtoreadlist(self):
        annualize = False
        myDB = db.DBConnection()
        readlist = myDB.selectone("SELECT * from issues where IssueID=?", [self.IssueID]).fetchone()
        if readlist is None:
            logger.fdebug(self.module + ' Checking against annuals..')
            readlist = myDB.selectone("SELECT * from annuals where IssueID=?", [self.IssueID]).fetchone()
            if readlist is None:
                logger.error(self.module + ' Cannot locate IssueID - aborting..')
                return
            else:
                annualize = True
        comicinfo = myDB.selectone("SELECT * from comics where ComicID=?", [readlist['ComicID']]).fetchone()
        logger.info(self.module + ' Attempting to add issueid ' + readlist['IssueID'])
        if comicinfo is None:
            logger.info(self.module + ' Issue not located on your current watchlist. I should probably check story-arcs but I do not have that capability just yet.')
        else:
            locpath = None
            if mylar.MULTIPLE_DEST_DIRS is not None and mylar.MULTIPLE_DEST_DIRS != 'None' and os.path.join(mylar.MULTIPLE_DEST_DIRS, os.path.basename(comicinfo['ComicLocation'])) != comicinfo['ComicLocation']:
                logger.fdebug(self.module + ' Multiple_dest_dirs:' + mylar.MULTIPLE_DEST_DIRS)
                logger.fdebug(self.module + ' Dir: ' + comicinfo['ComicLocation'])
                logger.fdebug(self.module + ' Os.path.basename: ' + os.path.basename(comicinfo['ComicLocation']))
                pathdir = os.path.join(mylar.MULTIPLE_DEST_DIRS, os.path.basename(comicinfo['ComicLocation']))
                if os.path.exists(os.path.join(pathdir, readlist['Location'])):
                    locpath = os.path.join(pathdir, readlist['Location'])
                else:
                    if os.path.exists(os.path.join(comicinfo['ComicLocation'], readlist['Location'])):
                        locpath = os.path.join(comicinfo['ComicLocation'], readlist['Location'])
            else:
                if os.path.exists(os.path.join(comicinfo['ComicLocation'], readlist['Location'])):
                    locpath = os.path.join(comicinfo['ComicLocation'], readlist['Location'])

            if not locpath is None:
                comicissue = readlist['Issue_Number']
                comicname = comicinfo['ComicName']
                dspinfo = comicname + ' #' + comicissue
                if annualize:
                    if mylar.ANNUALS_ON:
                        comicissue = 'Annual ' + readlist['Issue_Number']
                        dspinfo = comicname + ' Annual #' + readlist['Issue_Number']
                    else:
                        comicname = comicinfo['ComicName'] + ' Annual'
                        dspinfo = comicname + ' #' + comicissue
                ctrlval = {"IssueID":       self.IssueID}
                newval = {"DateAdded":      helpers.today(),
                          "Status":         "Added",
                          "ComicID":        readlist['ComicID'],
                          "Issue_Number":   comicissue,
                          "IssueDate":      readlist['IssueDate'],
                          "SeriesYear":     comicinfo['ComicYear'],
                          "ComicName":      comicname,
                          "Location":       locpath}

                myDB.upsert("readlist", newval, ctrlval)
                logger.info(self.module + ' Added ' + dspinfo + ' to the Reading list.')
        return

    def markasRead(self):
        myDB = db.DBConnection()
        if self.IssueID:
            issue = myDB.selectone('SELECT * from readlist WHERE IssueID=?', [self.IssueID]).fetchone()
            if issue['Status'] == 'Read':
                NewVal = {"Status":  "Added"}
            else:
                NewVal = {"Status":    "Read"}

            NewVal['StatusChange'] = helpers.today()

            CtrlVal = {"IssueID":  self.IssueID}
            myDB.upsert("readlist", NewVal, CtrlVal)
            logger.info(self.module + ' Marked ' + issue['ComicName'] + ' #' + str(issue['Issue_Number']) + ' as Read.')
        elif self.IssueArcID:
            issue = myDB.selectone('SELECT * from readinglist WHERE IssueArcID=?', [self.IssueArcID]).fetchone()
            if issue['Status'] == 'Read':
                NewVal = {"Status":    "Added"}
            else:
                NewVal = {"Status":    "Read"}
            NewVal['StatusChange'] = helpers.today()
            CtrlVal = {"IssueArcID":  self.IssueArcID}
            myDB.upsert("readinglist", NewVal, CtrlVal)
            logger.info(self.module + ' Marked ' +  issue['ComicName'] + ' #' + str(issue['IssueNumber']) + ' as Read.')

        return

    def syncreading(self):
        #3 status' exist for the readlist.
        # Added (Not Read) - Issue is added to the readlist and is awaiting to be 'sent' to your reading client.
        # Read - Issue has been read
        # Not Read - Issue has been downloaded to your reading client after the syncfiles has taken place.
        module = '[READLIST-TRANSFER]'
        myDB = db.DBConnection()
        readlist = []
        cidlist = []
        sendlist = []

        if self.filelist is None:
            rl = myDB.select('SELECT * FROM readlist WHERE Status="Added"')
            if rl is None:
                logger.info(module + ' No issues have been marked to be synced. Aborting syncfiles')
                return

            for rlist in rl:
                readlist.append({"filepath": rlist['Location'],
                                 "issueid":  rlist['IssueID'],
                                 "comicid":  rlist['ComicID']})

        else:
            readlist = self.filelist

        if len(readlist) > 0:

            for clist in readlist:
                if clist['filepath'] == 'None' or clist['filepath'] is None:
                    logger.warn(module + ' There was a problem with ComicID/IssueID: [' + clist['comicid'] + '/' + clist['issueid'] + ']. I cannot locate the file in the given location (try re-adding to your readlist)[' + clist['filepath'] + ']')
                    continue
                else:
#                    multiplecid = False
#                    for x in cidlist:
#                        if clist['comicid'] == x['comicid']:
#                            comicid = x['comicid']
#                            comiclocation = x['location']
#                            multiplecid = True

#                    if multiplecid == False:
#                        cid = myDB.selectone("SELECT * FROM comics WHERE ComicID=?", [clist['comicid']]).fetchone()
#                        if cid is None:
#                            continue
#                        else:
#                            comiclocation = cid['ComicLocation']
#                            comicid = cid['ComicID']

#                    if mylar.MULTIPLE_DEST_DIRS is not None and mylar.MULTIPLE_DEST_DIRS != 'None' and os.path.join(mylar.MULTIPLE_DEST_DIRS, os.path.basename(comiclocation)) != comiclocation:
#                        logger.fdebug(module + ' Multiple_dest_dirs:' + mylar.MULTIPLE_DEST_DIRS)
#                        logger.fdebug(module + ' Dir: ' + comiclocation)
#                        logger.fdebug(module + ' Os.path.basename: ' + os.path.basename(comiclocation))
#                        pathdir = os.path.join(mylar.MULTIPLE_DEST_DIRS, os.path.basename(comiclocation))
                     if os.path.exists(clist['filepath']):
                            sendlist.append({"issueid":  clist['issueid'],
                                             "filepath": clist['filepath'],
                                             "filename": os.path.split(clist['filepath'])[1]})
#                     else:
#                         if os.path.exists(os.path.join(comiclocation, clist['filename'])):
#                                sendlist.append({"issueid":   clist['issueid'],
#                                                 "filepath":  comiclocation,
#                                                 "filename":  clist['filename']})
#                    else:
#                        if os.path.exists(os.path.join(comiclocation, clist['filename'])):
#                            sendlist.append({"issueid":   clist['issueid'],
#                                             "filepath":  comiclocation,
#                                             "filename":  clist['filename']})
                     else:
                         logger.warn(module + ' ' + clist['filepath'] + ' does not exist in the given location. Remove from the Reading List and Re-add and/or confirm the file exists in the specified location')
                         continue

#                    #cidlist is just for this reference loop to not make unnecessary db calls if the comicid has already been processed.
#                    cidlist.append({"comicid":   clist['comicid'],
#                                    "issueid":   clist['issueid'],
#                                    "location":  comiclocation})  #store the comicid so we don't make multiple sql requests

            if len(sendlist) == 0:
                logger.info(module + ' Nothing to send from your readlist')
                return

            logger.info(module + ' ' + str(len(sendlist)) + ' issues will be sent to your reading device.')

            # test if IP is up.
            import shlex
            import subprocess

            #fhost = mylar.TAB_HOST.find(':')
            host = mylar.TAB_HOST[:mylar.TAB_HOST.find(':')]

            if 'windows' not in mylar.OS_DETECT.lower():
                cmdstring = str('ping -c1 ' + str(host))
            else:
                cmdstring = str('ping -n 1 ' + str(host))
            cmd = shlex.split(cmdstring)
            try:
                output = subprocess.check_output(cmd)
            except subprocess.CalledProcessError, e:
                logger.info(module + ' The host {0} is not Reachable at this time.'.format(cmd[-1]))
                return
            else:
                if 'unreachable' in output:
                    logger.info(module + ' The host {0} is not Reachable at this time.'.format(cmd[-1]))
                    return
                else:
                    logger.info(module + ' The host {0} is Reachable. Preparing to send files.'.format(cmd[-1]))

            success = mylar.ftpsshup.sendfiles(sendlist)

            if len(success) > 0:
                for succ in success:
                    newCTRL = {"issueid":  succ['issueid']}
                    newVAL = {"Status": 'Downloaded',
                              "StatusChange": helpers.today()}
                    myDB.upsert("readlist", newVAL, newCTRL)

