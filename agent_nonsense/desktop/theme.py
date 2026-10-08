STYLE = """
QWidget { color: #282b3c; font-size: 13px; }
QMainWindow, #workspace, #scrollContent { background: #f5f6fa; }
#sidebar { background: #fcfcff; border-right: 1px solid #e6e8f0; }
QLabel { background: transparent; }
QLabel[muted="true"] { color: #81869b; }
#brand { font-size: 23px; font-weight: 700; }
#pageTitle { font-size: 28px; font-weight: 700; }
#subtitle { color: #81869b; font-size: 14px; }
#eyebrow { color: #8a82b0; font-size: 11px; font-weight: 600; }
#card { background: white; border: 1px solid #e6e8f0; border-radius: 16px; }
#heroCard { background: #eeeafa; border: 1px solid #e2dcf4; border-radius: 18px; }
#metricValue { font-size: 25px; font-weight: 650; }
#cardTitle { font-size: 16px; font-weight: 650; }
#heroTitle { font-size: 23px; font-weight: 700; color: #423664; }
#pill { background: #eeebfa; color: #7160a7; padding: 7px 12px; border-radius: 12px; }
#pill[state="running"] { background: #e3f3ec; color: #328367; }
#pill[state="error"] { background: #ffeded; color: #be5261; }
#notice { background: #eeebfa; color: #625184; padding: 10px 14px; border-radius: 9px; }
#notice[error="true"] { background: #ffeded; color: #b34857; }
QPushButton { background: white; border: 1px solid #dfe2ed; border-radius: 9px;
  padding: 10px 16px; font-weight: 550; }
QPushButton:hover { background: #f3f0fc; border-color: #c6b8e7; }
QPushButton:pressed { background: #e7e0f6; }
QPushButton:disabled { background: #f2f3f7; color: #a1a5b5; border-color: #eaecf2; }
QPushButton[primary="true"] { background: #8064bf; color: white; border: 1px solid #8064bf; }
QPushButton[primary="true"]:hover { background: #7156af; }
QPushButton[primary="true"]:disabled { background: #c8bcdf; border-color: #c8bcdf; }
QPushButton[danger="true"] { color: #b24f62; background: #fff1f3; border-color: #f3d7dd; }
QPushButton[nav="true"] { text-align: left; padding: 13px 16px; border: none; background: transparent; color: #777d94; }
QPushButton[nav="true"]:hover { background: #f1eef9; }
QPushButton[nav="true"]:checked { background: #eae4f8; color: #7052af; font-weight: 650; }
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { background: #f9f9fc; border: 1px solid #e2e4ef;
  border-radius: 8px; padding: 9px 10px; min-height: 20px; selection-background-color: #cfc0ee; }
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus,
QPlainTextEdit:focus { border-color: #a48cd1; }
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled { color: #999fb2; background: #f3f4f8; }
QComboBox::drop-down { border: none; width: 23px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #eae4f8; padding: 5px; }
QPlainTextEdit, QTextBrowser { border: 1px solid #e5e7f0; border-radius: 10px; background: #fcfcfe;
  padding: 14px; selection-background-color: #d8c9f2; }
#console { background: #242738; color: #d9def0; border-color: #242738; }
QListWidget { background: transparent; border: none; outline: none; }
QListWidget::item { padding: 12px 10px; border-radius: 8px; margin-bottom: 5px; }
QListWidget::item:selected { background: #eae4f8; color: #7052af; }
QTableWidget { background: white; border: 1px solid #e6e8f0; border-radius: 10px; gridline-color: #eff0f6;
  selection-background-color: #eeebfa; selection-color: #66508e; }
QHeaderView::section { background: #f5f5fa; color: #787e94; padding: 12px; border: none; }
QTableWidget::item { padding: 8px; border-bottom: 1px solid #f0f1f6; }
QCheckBox { spacing: 9px; padding: 5px 0; }
QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #cbd0df; border-radius: 5px; background: white; }
QCheckBox::indicator:checked { background: #8064bf; border-color: #8064bf; image: none; }
QScrollArea { background: transparent; border: none; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 3px; }
QScrollBar::handle:vertical { background: #d2d4e2; border-radius: 3px; min-height: 30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 8px; margin: 3px; }
QScrollBar::handle:horizontal { background: #d2d4e2; border-radius: 3px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }
QToolTip { background: #302c44; color: white; padding: 8px; border: none; }
QSplitter::handle { background: transparent; width: 12px; }
"""
