"""Offline help; shortcut rows are generated from the actual window actions."""
from html import escape
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QDialogButtonBox


GUIDE = """<div dir="rtl">
<h2>מדריך משתמש</h2>
<p><b>פתיחת Playlist:</b> בחרו Open Playlist בתפריט File או בכפתור, ובחרו JSON של Cockpit.</p>
<p><b>התצוגה:</b> השירים מתקדמים מלמעלה למטה בעמודה, ואז לעמודה הבאה לפי כיוון LTR/RTL. המספור כולל שירים בלבד.</p>
<p><b>בחירה וגרירה:</b> לחיצה בוחרת שיר. Ctrl+Click מוסיף או מסיר שירים; Shift+Click בוחר רצף ומדלג על קטגוריות. גררו שיר מסומן כדי להעביר את כל הבחירה יחד, תוך שמירת סדרה. הקו הצהוב בין הפריטים מציין את מקום ההכנסה. Escape מבטל גרירה.</p>
<p><b>Categories:</b> כותרות מודגשות וממורכזות ברצף, ללא מספר. אפשר להכניס שירים לפניהן ואחריהן.</p>
<p><b>הוספה:</b> לחצן ימני על פריט → Add Song לבחירת קובץ שיר, או Add Category להזנת שם. הפריט נוסף לפני הפריט שנלחץ. ברשימה ריקה לחצו ימנית על התצוגה.</p>
<p><b>הסרה:</b> Remove Song מסיר את השיר שנלחץ, או את כל הבחירה אם השיר חלק ממנה. לחצן ימני על שיר מחוץ לבחירה בוחר רק אותו. Remove Category מסיר רק את הכותרת לאחר אישור. קובצי המוזיקה אינם נמחקים.</p>
<p><b>Save:</b> שומר לקובץ הפעיל עם אישור לפני הדריסה הראשונה במהלך הפעלת התוכנה. <b>Save As:</b> שומר לנתיב שנבחר והופך אותו לקובץ הפעיל. אין שמירה אוטומטית.</p>
<p><b>RTL / LTR:</b> הכפתור ליד Open Playlist מחליף את כיוון העמודות בלבד ושומר את ההעדפה. סדר הנתונים אינו משתנה.</p>
<p><b>Font Size:</b> בתפריט View אפשר להגדיל, להקטין או לאפס את הפונט. גובה הפריטים והפריסה מתעדכנים.</p>
<p><b>Column Width:</b> בתפריט View אפשר להגדיל או להקטין את הרוחב האחיד של כל העמודות. עמודות רחבות מציגות יותר מהשם; צרות מאפשרות יותר עמודות במסך. הרוחב נשמר בין הפעלות. Reset מחזיר לפריסה האוטומטית לפי הפונט והחלון. ייתכן צורך בגלילה אופקית.</p>
</div>"""

ABOUT = """<div style="text-align:center"><h2>Cockpit Playlist Editor</h2>
<p>Visual Playlist Editor for Cockpit</p>
<p>A fast visual tool for organizing large Cockpit playlists.</p>
<p>© 2026 Eyal Cohen</p></div>"""


def shortcut_html(window):
    rows = []
    for action in window.findChildren(QAction):
        keys = [key.toString(QKeySequence.NativeText) for key in action.shortcuts() if not key.isEmpty()]
        if keys:
            rows.append(f"<tr><td>{escape(' / '.join(keys))}</td><td>{escape(action.text())}</td></tr>")
    rows += ["<tr><td>Ctrl+Click</td><td>בחירה מרובה / ביטול בחירה</td></tr>",
             "<tr><td>Shift+Click</td><td>בחירת רצף שירים</td></tr>",
             "<tr><td>Escape</td><td>Cancel Drag &amp; Drop</td></tr>"]
    return '<h2>Keyboard Shortcuts</h2><table cellpadding="8">' + ''.join(rows) + '</table>'


def show_help_dialog(window, topic):
    dialog = window.help_dialogs.get(topic)
    if dialog is None:
        dialog = QDialog(window)
        dialog.setWindowTitle(topic)
        dialog.resize(640, 530 if topic != "About Cockpit Playlist Editor" else 300)
        layout = QVBoxLayout(dialog)
        browser = QTextBrowser()
        browser.setOpenExternalLinks(False)
        browser.setStyleSheet("QTextBrowser { background: #16222f; color: #e6edf5; padding: 12px; font-size: 14px; }")
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.close)
        layout.addWidget(buttons)
        dialog.browser = browser
        window.help_dialogs[topic] = dialog
    dialog.browser.setHtml(GUIDE if topic == "Help / User Guide" else
                           shortcut_html(window) if topic == "Keyboard Shortcuts" else ABOUT)
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog
