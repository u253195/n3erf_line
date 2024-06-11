import os
from argparse import ArgumentParser
from flask import Flask, request, abort
import requests
import json
import sys
import ssl
import ftplib
from Crypto.Cipher import AES
from binascii import b2a_hex, a2b_hex

from datetime import datetime
from bs4 import BeautifulSoup
from linebot import (
    LineBotApi, WebhookHandler
)
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage
)

app = Flask(__name__)
channel_secret = os.getenv('LINE_CHANNEL_SECRET', None)
channel_access_token = os.getenv('LINE_CHANNEL_ACCESS_TOKEN', None)
uidlist=[]
namelist=[]
helps="我只會這些：\n"
helps=helps+"-核電廠即時資訊：輸入\n"
helps=helps+"核電廠即時資訊\n"
helps=helps+"  3個核能廠的即時發電資訊\n"
helps=helps+"-環境輻射：輸入\n"
helps=helps+"環境輻射即時監測X\n"
helps=helps+"  X為1，2，3，4代表核一，核二，核三，龍門\n"
helps=helps+"-核三廠會議排程：輸入\n"
helps=helps+"會議排程\n"
helps=helps+"-核三廠運轉狀況：輸入\n"
helps=helps+"運轉狀況\n"
helps = helps+"-ERF電腦點資料：輸入\n"
helps =  helps+"erf@XXXXXX\n"
helps =  helps+"  XXXXXX為電腦點名稱如MAQ001\n"
helps = helps+"-近3日為結案請修單：輸入\n"
helps =  helps+"swr@uX\n"
helps=helps+"  X為1，2代表一號機，二號機\n"

if channel_secret is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)
    
def compose16(akey):
    count=len(akey)
    add=16-(count%16)
    bkey=akey+('\0'*add)
    return bkey
class prpcrypt():
    def __init__(self, key):
        self.key = compose16(key)
        self.mode = AES.MODE_CBC
 
    #加密函數，如果text不是16的倍數【加密文本text必須為16的倍數！】，那就補足為16的倍數
    def encrypt(self, text):
        cryptor = AES.new(self.key, self.mode, self.key)
        #這裏密鑰key 長度必須為16（AES-128）、24（AES-192）、或32（AES-256）Bytes 長度.目前AES-128足夠用
        text=compose16(text)
        self.ciphertext = cryptor.encrypt(text)
        #因為AES加密時候得到的字符串不一定是ascii字符集的，輸出到終端或者保存時候可能存在問題
        #所以這裏統一把加密後的字符串轉化為16進制字符串
        return b2a_hex(self.ciphertext)
     
    #解密後，去掉補足的空格用strip() 去掉
    def decrypt(self, text):
        cryptor = AES.new(self.key, self.mode, self.key)
        plain_text = cryptor.decrypt(a2b_hex(text)).decode("utf-8")
        return plain_text.rstrip('\0')

def ftpget(ftpsrv,userid,userpwd,rdir,fname):
    session=ftplib.FTP_TLS(ftpsrv,userid,userpwd)
    afile=open(fname,'rb')
    session.store()
    afile.close()
    session.quit
def ftpput(ftpsrv,userid,userpwd,rdir,fname):
    session=ftplib.FTP_TLS(ftpsrv,userid,userpwd)
    afile=open(fname,'w')
    session.retr()
    afile.close()
    session.quit
  
def loaduid(fname):
    aeskey='253195@tpcn3'
    pc=prpcrypt((aeskey))
    tmplist=[]
    fo=open(fname,'r')
    for line in fo.readlines():
        line=line.strip()
        if len(line)>0:
            if line[0]!='#':
                tmplist.append(pc.decrypt(line))
    return tmplist
def encryptID(aid):
    aeskey='253195@tpcn3'
    pc=prpcrypt(aeskey)
    return pc.encrypt(aid).decode("utf-8")
def loaduser(fname):
    aeskey='253195@tpcn3'
    pc=prpcrypt((aeskey))
    global uidlist, namelist
    namelist=[]
    uidlist=[]
    fo=open(fname,'r')
    for line in fo.readlines():
        line=line.strip()
        if len(line)>0:
            if line[0]!='#':
                uidlist.append(pc.decrypt(line))
            else:
                namelist.append(line)
    fo.close()
def loaduserfromnet(url):
    # Define the local filename to save data
    local_file = 'local_copy.txt'
    # Download remote and save locally
    data = requests.get(url)
    # Save file data to local copy
    file=open(local_file, 'wb')
    file.write(data.content)
    file.close()
    global uidlist
    uidlist=loaduid('local_copy.txt')
                    
def adduser(auser):
    global namelist,uidlist
    idx=auser.find('#')
    uname='#'+auser[0:idx-1]
    uid=auser[idx+1:len(auser)]
    namelist.append(uname)
    uidlist.append(uid)
    print(uname)
    print(uid)
#    erfaddlineuser(uname,uid)
    fo=open('userid.txt','a')
    fo.write(uname+'\n')
    fo.write(uid+'\n')
    fo.close()
def deluser(auser):
    global namelist,uidlist
    idx=auser.find('#')
    uname='#'+auser[0:idx-1]
    uid=auser[idx+1:len(auser)]
    namelist.append(uname)
    uidlist.append(uid)
    fo=open('userid.txt','a')
    fo.writelines(uname)
    fo.writelines(uid)
    fo.close()
def getusers():
    loaduser('userid.txt')
    rst=''
    for aname in namelist:
      rst=rst+aname+'\n'
    return rst
    
    
# Channel Access Token
line_bot_api = LineBotApi(channel_access_token)
# Channel Secret
handler = WebhookHandler(channel_secret)

#uidlist=loaduid('userid.txt')
loaduser('userid.txt')
#loaduserfromnet('https://wapp4.taipower.com.tw/nsis/operation/userid.txt')

# 監聽所有來自 /callback 的 Post Request
@app.route("/callback", methods=['POST'])
def callback():
    # get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # handle webhook body
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

def erfTest(plant,pid):
    urlhead='https://service.taipower.com.tw/wapp4/n3erf/ds_n3.dll/datasnap/rest/tservermethods1/p_jtest()'
    url=urlhead
    #myResponse=requests.get(url,auth=("2531951", "253195"))
    myResponse=requests.get(url, verify=False)
#    rst=myResponse.content.decode('utf-8')
    rst=myResponse.content
    if (myResponse.ok):
        jData=json.loads(rst)
        l1=jData['result']
        return l1[0]
    else:
        return -10.0
def erfValue(plant,pid):
    urlhead='https://service.taipower.com.tw/wapp4/n3erf/ds_n3.dll/datasnap/rest/tservermethods1/p_cvt_pid_w('
    url=urlhead+plant+',"'+pid.upper()+'")'
    #myResponse=requests.get(url,auth=("2531951", "253195"))
    myResponse=requests.get(url, verify=False)
#    rst=myResponse.content.decode('utf-8')
    rst=myResponse.content
    if (myResponse.ok):
        jData=json.loads(rst)
        l1=jData['result']
        return l1[0]
    else:
        return -10.0
def     erfaddlineuser(uname,uid):
#    urlhead='https://nu3app.taipower.com.tw:8080/n3erf/n3erfwb.dll/datasnap/rest/#tservermethods1/addlineuser("'
    urlhead='https://service.taipower.com.tw/wapp4/n3erf/ds_n3.dll/datasnap/rest/tservermethods1/addlineuser("'
    url=urlhead+uname+'","'+uid+'")'
    #myResponse=requests.get(url,auth=("2531951", "253195"))
    myResponse=requests.get(url, verify=False)
    rst=myResponse.content.decode('utf-8')
    if (myResponse.ok):
        jData=json.loads(rst)
        l1=jData['result']
        return l1[0]
    else:
        return -10.0

def erfValueStr(pid):
    v1=erfValue('1',pid)
    v2=erfValue('2',pid)
    return ('[#1]%8.2f, [#2]%8.2f'%(v1,v2))
def erfteststr():
    v1=erfTest('1','abcdef')
    return('testvaule:%8.2f'%(v1))
def NuclearPower():
    url='https://www.nusc.gov.tw/nuclearlive'
    myResponse = requests.get(url)
    name_box=BeautifulSoup(myResponse.text,'html.parser')
#    name_box=soup.find('div',attrs={'id':'page-html'})
    timebox=name_box.find('span', attrs={'class':'tx','id':'timeX'})
    N11STATUSbox=name_box.find('span',attrs={'class':'tx1','id':'N11STATUS'})
    N11RATEbox=name_box.find('span',attrs={'class':'tx2','id':'N11RATEID'})
    N11GENbox=name_box.find('span',attrs={'class':'tx2','id':'N11GENID'})
    N12STATUSbox=name_box.find('span',attrs={'class':'tx1','id':'N12STATUS'})
    N12RATEbox=name_box.find('span',attrs={'class':'tx2','id':'N12RATEID'})
    N12GENbox=name_box.find('span',attrs={'class':'tx2','id':'N12GENID'})
    N21STATUSbox=name_box.find('span',attrs={'class':'tx1','id':'N21STATUS'})
    N21RATEbox=name_box.find('span',attrs={'class':'tx2','id':'N21RATEID'})
    N21GENbox=name_box.find('span',attrs={'class':'tx2','id':'N21GENID'})
    N22STATUSbox=name_box.find('span',attrs={'class':'tx1','id':'N22STATUS'})
    N22RATEbox=name_box.find('span',attrs={'class':'tx2','id':'N22RATEID'})
    N22GENbox=name_box.find('span',attrs={'class':'tx2','id':'N22GENID'})
    N31STATUSbox=name_box.find('span',attrs={'class':'tx1','id':'N31STATUS'})
    N31RATEbox=name_box.find('span',attrs={'class':'tx2','id':'N31RATEID'})
    N31GENbox=name_box.find('span',attrs={'class':'tx2','id':'N31GENID'})
    N32STATUSbox=name_box.find('span',attrs={'class':'tx1','id':'N32STATUS'})
    N32RATEbox=name_box.find('span',attrs={'class':'tx2','id':'N32RATEID'})
    N32GENbox=name_box.find('span',attrs={'class':'tx2','id':'N32GENID'})
    LL1='核能一廠\n#1:'+N11STATUSbox.text+'('+N11RATEbox.text+','+N11GENbox.text+')\n#2:'+N12STATUSbox.text+'('+N12RATEbox.text+','+N12GENbox.text+')'
    LL2='核能二廠\n#1:'+N21STATUSbox.text+'('+N21RATEbox.text+','+N21GENbox.text+')\n#2:'+N22STATUSbox.text+'('+N22RATEbox.text+','+N22GENbox.text+')'
    LL3='核能三廠\n#1:'+N31STATUSbox.text+'('+N31RATEbox.text+','+N31GENbox.text+')\n#2:'+N32STATUSbox.text+'('+N32RATEbox.text+','+N32GENbox.text+')'
    return(timebox.text.strip()+'\n'+LL1+'\n'+LL2+'\n'+LL3)
def NuclearRadiation(plant):
    url = 'https://www.nusc.gov.tw/gammadetect/npp'+plant+'.html'
    myResponse = requests.get(url)
    name_box=BeautifulSoup(myResponse.text,'html.parser')
    N0name=name_box.find('span',attrs={'class':'gamma_bk15','id':'monName_0_0'})
    N0value=name_box.find('span',attrs={'class':'gamma_bk15','id':'monValue_0_0'})
    N0time=name_box.find('span',attrs={'class':'gamma_bk13','id':'monTime_0_0'})
    N1name=name_box.find('span',attrs={'class':'gamma_bk15','id':'monName_0_1'})
    N1value=name_box.find('span',attrs={'class':'gamma_bk15','id':'monValue_0_1'})
    N1time=name_box.find('span',attrs={'class':'gamma_bk13','id':'monTime_0_1'})
    N2name=name_box.find('span',attrs={'class':'gamma_bk15','id':'monName_0_2'})
    N2value=name_box.find('span',attrs={'class':'gamma_bk15','id':'monValue_0_2'})
    N2time=name_box.find('span',attrs={'class':'gamma_bk13','id':'monTime_0_2'})
    N3name=name_box.find('span',attrs={'class':'gamma_bk15','id':'monName_0_3'})
    N3value=name_box.find('span',attrs={'class':'gamma_bk15','id':'monValue_0_3'})
    N3time=name_box.find('span',attrs={'class':'gamma_bk13','id':'monTime_0_3'})
    N4name=name_box.find('span',attrs={'class':'gamma_bk15','id':'monName_0_4'})
    N4value=name_box.find('span',attrs={'class':'gamma_bk15','id':'monValue_0_4'})
    N4time=name_box.find('span',attrs={'class':'gamma_bk13','id':'monTime_0_4'})
    if plant =='1':
        head0='核一廠環境輻射即時監測'
    elif plant =='2':
        head0='核二廠環境輻射即時監測'
    elif plant =='3':
        head0='核三廠環境輻射即時監測'
    elif plant =='4':
        head0='龍門電廠環境輻射即時監測'
    else:
        head0=''
    r0=N0time.text+N0name.text+N0value.text+'\n'
    r1=N1time.text+N1name.text+N1value.text+'\n'
    r2=N2time.text+N2name.text+N2value.text+'\n'
    r3=N3time.text+N3name.text+N3value.text+'\n'
    r4=N4time.text+N4name.text+N4value.text
    rst=r0+r1+r2+r3+r4
    if len(head0) == 0:
        tmprst='請輸入正確的電廠代碼'
    else:
        tmprst=head0+'\n'+rst
    return(tmprst)

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    global helps
    global uidlist
    message = TextSendMessage(text="您說了: " + event.message.text)
    src = event.source.user_id
#    if 'uidlist' in globals():
#        print('uidlist defined')
#    else:
#        uidlist=[]
#        print('loading userid')
#        uidlist=loaduid('userid.txt')
        
    if src in uidlist:
        rcvmsg = "我不懂: " + event.message.text
        if event.message.text == "核電廠即時資訊":
            sss=NuclearPower()
        elif event.message.text == "環境輻射即時監測1":
            sss=NuclearRadiation('1')
        elif event.message.text == "環境輻射即時監測2":
            sss=NuclearRadiation('2')
        elif event.message.text == "環境輻射即時監測3":
            sss=NuclearRadiation('3')
        elif event.message.text == "環境輻射即時監測4":
            sss=NuclearRadiation('4')
        elif event.message.text == "使用說明":
            sss=helps
        elif event.message.text == "發電量":
            sss=erfValueStr('MAQ001')
        elif event.message.text == "erftest":
            sss=erfteststr()
        elif event.message.text[:4]=="erf@":
            erfpid=event.message.text[4:len(event.message.text)]
            sss=erfValueStr(erfpid)
        elif event.message.text == "會議排程":
            sss="https://service.taipower.com.tw/wapp4/operation/n3web/g0item4.htm"
        elif event.message.text == "運轉狀況":
            sss="https://service.taipower.com.tw/wapp4/operation/n3web/g0item1.htm"
        elif event.message.text == "swr@u1":
            sss="https://service.taipower.com.tw/wapp4/operation/n3web/g0item7.htm"
        elif event.message.text == "swr@u2":
            sss="https://service.taipower.com.tw/wapp4/operation/n3web/g0item8.htm"
        elif event.message.text[:8]=="useradd@":
            if src==uidlist[0]:
                userinfo=event.message.text[8:len(event.message.text)]
                adduser(userinfo)
        elif event.message.text[:8]=="userdel@":
            if src==uidlist[0]:
                userinfo=event.message.text[8:len(event.message.text)]
                deluser(userinfo)
        elif event.message.text[:8]=="getusers":
            if src==uidlist[0]:
                sss=getusers()
        
        else:
            sss=rcvmsg+"\n"+helps
    else:
        sss = '對不起！您沒有使用權，請用以下驗證碼向管理員申請\n'+encryptID(src)

    amsg = TextSendMessage(text=sss)
    line_bot_api.reply_message(event.reply_token,amsg)


if __name__ == "__main__":
#    uidlist=loaduid('userid.txt')
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
