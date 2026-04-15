1. load_dotenv 要加上參數 override=True
2. 我的題目不只會有數字，因為會有來自不同 team 的需求，會對應到不同的 gitea issue url.
文字會像是 P260 ，這種前面有P的對應到的 issue url 是 drc:8080/gitea/PDKD-3-04/perl_scripts/issues/260
如果是帶有 CN 的像是 CN49，對應的 issue url 是 drc:8080/gitea/CN_TEAM/MtM_DRC_QC_script_request/issues/49
如果是 SNPS61 這種，對應的 issue url 是 drc:8080/gitea/Synopsys/qc_script/issues/61

如果是純數字的話，就是 drc:8080/gitea/PDKD-3-04/QC_requests/issues/301 這樣
是否可以把這種對應的 URL 的 mapping format 整理成一個邏輯，讓我可以在 admin 頁面設定，並且要在 topic 或是數字可以點進超連結

3. TOPIC 的欄位想要加寬，PATH 的欄位也想要加寬，是否可以讓我能夠快速地調整?
4. Path 裡面的文字跟表格的邊界想要有一些間距，不要直接貼邊
5. Unneeded 的狀態目前沒有顯示，幫我用灰色顯示，並且要有文字在 label 中
6. 匯入的時候幫我檢查是否有題號重覆，如果有的話跳出 warning 
7. owner 有可能會需要更改，這個可以幫我做權限控管，我不太確定是否要區分 admin 跟 superuser?
8. Closing rate 需要多加含有 MtM 的數據，一欄為含有 MtM，一欄位不包含 MtM
9. Closing Rate 的 Trend 顯示方式會因為每週新增跟關掉的題目數量而有所不同，現在的算法不太正確，我會有一個表格內含近幾周 UAT/TBD/Dev/Close 的數量，可以根據這個表格來作圖
10. 我想要 Tracker 跟 Closed 的頁面可以直接被 Read only，不用登入。
11. 題目的 Topic / Path/ 需要能夠被修改或是刪除，並且告訴我要怎麼新增題目?
12. 欄位名稱是否可以做成凍結窗格? 這樣在滑動的時候比較方便看
13. 我這邊有內部 mail 寄送的範例程式碼的更新，依照這方式來做信件功能
```
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
import time

receiver_list = ["xxx@tsmc.com", "..."]
ip = "10.234.8.22"
port = 2525

msg = MIMEMultipart('alternative')
msg['Subject'] = "Auto Mail"
msg['From'] = "p_drc@tsmc.com"

def main():
    timestamp = time.time()
    readable_time = str(datetime.fromtimestamp(timestamp))
    msg.attach(MIMEText(readable_time, "plain"))

    s = smtplib.SMTP(ip, port)
    s.sendmail(msg["From"], receiver_list, msg.as_string())

    s.quit()
    print("send mail to {} sucess !".format(", ".join(receiver_list)))

if __name__ == "__main__":
    main()

```