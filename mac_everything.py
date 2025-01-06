import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import Qt, QTimer, Signal, Slot
from PySide6.QtGui import QIcon, QKeySequence, QShortcut, QPalette, QColor, QFont
from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QLineEdit,
    QTreeWidget,
    QTreeWidgetItem,
    QLabel,
    QHeaderView,
    QStyle,
    QStyleFactory,
)

class FileTreeWidget(QTreeWidget):
    """自定义树形控件，实现自定义排序"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSortingEnabled(True)
        self.header().setStretchLastSection(False)
        self.header().setMinimumSectionSize(50)
        self.header().setDefaultSectionSize(100)

    def __lt__(self, other):
        """自定义排序方法"""
        column = self.treeWidget().sortColumn()
        if column == 2:  # 大小列
            return float(self.data(2, Qt.ItemDataRole.UserRole) or 0) < float(other.data(2, Qt.ItemDataRole.UserRole) or 0)
        elif column == 3:  # 时间列
            return float(self.data(3, Qt.ItemDataRole.UserRole) or 0) < float(other.data(3, Qt.ItemDataRole.UserRole) or 0)
        return self.text(column) < other.text(column)

def format_size_kb(size_in_bytes: int) -> str:
    """格式化文件大小为KB"""
    kb_size = max(1, size_in_bytes // 1024)
    return f"{kb_size:,} KB"

def format_size_full(size_in_bytes: int) -> str:
    """格式化文件大小（完整格式）"""
    if size_in_bytes < 1024:
        return f"{size_in_bytes:,} B"
    elif size_in_bytes < 1024 * 1024:
        return f"{size_in_bytes/1024:.0f} KB"
    elif size_in_bytes < 1024 * 1024 * 1024:
        return f"{size_in_bytes/(1024*1024):.1f} MB"
    else:
        return f"{size_in_bytes/(1024*1024*1024):.2f} GB"

def format_time(timestamp: float) -> str:
    """格式化时间戳"""
    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%Y/%m/%d %H:%M")

class SearchWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Mac Everything")
        self.setMinimumSize(1000, 600)

        # 创建中心部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        # 创建搜索框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("输入搜索内容...")
        self.search_input.setMinimumHeight(30)
        font = self.search_input.font()
        font.setPointSize(13)
        self.search_input.setFont(font)
        layout.addWidget(self.search_input)

        # 创建状态标签
        self.status_label = QLabel()
        self.status_label.setFont(QFont("", 12))
        layout.addWidget(self.status_label)

        # 创建结果表格
        self.result_tree = FileTreeWidget()
        self.result_tree.setFont(QFont("", 12))
        self.result_tree.setAlternatingRowColors(True)
        self.result_tree.setRootIsDecorated(False)
        self.result_tree.setUniformRowHeights(True)
        self.result_tree.setColumnCount(4)
        self.result_tree.setHeaderLabels(["名称", "路径", "大小", "修改时间"])
        
        # 设置列宽和调整模式
        header = self.result_tree.header()
        for i in range(4):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        
        # 设置默认列宽
        header.resizeSection(0, 200)  # 名称列
        header.resizeSection(1, 400)  # 路径列
        header.resizeSection(2, 100)  # 大小列
        header.resizeSection(3, 150)  # 时间列
        
        # 设置滚动条始终显示
        self.result_tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.result_tree.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        # 设置滚动条样式，只针对滚动条组件
        scrollbar_style = """
            QScrollBar:vertical {
                width: 16px;
                margin: 0px;
            }
            QScrollBar:horizontal {
                height: 16px;
                margin: 0px;
            }
            QScrollBar::handle:vertical, QScrollBar::handle:horizontal {
                min-height: 30px;
                min-width: 30px;
                background: #A0A0A0;
            }
            QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {
                background: #808080;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
                height: 0px;
                width: 0px;
            }
        """
        self.result_tree.verticalScrollBar().setStyleSheet(scrollbar_style)
        self.result_tree.horizontalScrollBar().setStyleSheet(scrollbar_style)
        
        layout.addWidget(self.result_tree)

        # 设置搜索延迟定时器
        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)
        self.search_timer.timeout.connect(self.perform_search)

        # 连接信号
        self.search_input.textChanged.connect(self.on_search_text_changed)
        self.result_tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.result_tree.itemClicked.connect(self.on_item_clicked)
        self.result_tree.currentItemChanged.connect(self.on_current_item_changed)

        # 添加快捷键
        QShortcut(QKeySequence.StandardKey.Find, self, self.focus_search)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.clear_search)

        # 初始化状态
        self.last_search_text = ""
        self.center_on_screen()
        self.search_input.setFocus()

    def center_on_screen(self):
        """将窗口居中显示"""
        frame_geometry = self.frameGeometry()
        screen_center = self.screen().availableGeometry().center()
        frame_geometry.moveCenter(screen_center)
        self.move(frame_geometry.topLeft())

    @Slot()
    def focus_search(self):
        """聚焦到搜索框"""
        self.search_input.setFocus()
        self.search_input.selectAll()

    @Slot()
    def clear_search(self):
        """清空搜索框"""
        self.search_input.clear()

    @Slot(str)
    def on_search_text_changed(self, text: str):
        """搜索文本改变时的处理"""
        if text == self.last_search_text:
            return
        self.last_search_text = text
        self.search_timer.start()

    def perform_search(self):
        """执行搜索"""
        search_text = self.search_input.text().strip()
        
        if not search_text:
            self.result_tree.clear()
            self.status_label.clear()
            return

        self.status_label.setText("正在搜索...")
        self.result_tree.clear()

        try:
            # 使用 mdfind 搜索文件
            cmd = ["mdfind", "-name", search_text]
            process = subprocess.run(cmd, capture_output=True, text=True)
            
            if process.returncode != 0:
                raise Exception(f"搜索失败: {process.stderr}")

            results = [path for path in process.stdout.splitlines() if path.strip()]
            
            # 更新界面
            for path in results:
                try:
                    stat = os.stat(path)
                    name = os.path.basename(path)
                    directory = os.path.dirname(path)
                    size = format_size_kb(stat.st_size)
                    mtime = format_time(stat.st_mtime)

                    item = QTreeWidgetItem()
                    item.setText(0, name)
                    item.setText(1, directory)
                    item.setText(2, size)
                    item.setText(3, mtime)
                    
                    # 存储原始数据用于排序
                    item.setData(0, Qt.ItemDataRole.UserRole, path)
                    item.setData(2, Qt.ItemDataRole.UserRole, stat.st_size)
                    item.setData(3, Qt.ItemDataRole.UserRole, stat.st_mtime)
                    
                    self.result_tree.addTopLevelItem(item)
                except (FileNotFoundError, PermissionError):
                    continue

            # 更新状态
            count = len(results)
            if count > 0:
                self.status_label.setText(f"找到 {count} 个结果")
            else:
                self.status_label.setText("未找到结果")

        except Exception as e:
            self.status_label.setText(f"搜索出错: {str(e)}")

    @Slot(QTreeWidgetItem)
    def on_item_clicked(self, item: QTreeWidgetItem):
        """单击列表项时的处理"""
        self.update_status_for_item(item)

    @Slot(QTreeWidgetItem, QTreeWidgetItem)
    def on_current_item_changed(self, current: QTreeWidgetItem, previous: QTreeWidgetItem):
        """当前选中项改变时的处理"""
        if current:
            self.update_status_for_item(current)

    def update_status_for_item(self, item: QTreeWidgetItem):
        """更新状态栏显示选中项的详细信息"""
        try:
            path = item.data(0, Qt.ItemDataRole.UserRole)
            size_bytes = item.data(2, Qt.ItemDataRole.UserRole)
            if path and size_bytes is not None:
                self.status_label.setText(f"文件大小: {format_size_full(size_bytes)}")
        except:
            pass

    @Slot(QTreeWidgetItem)
    def on_item_double_clicked(self, item: QTreeWidgetItem):
        """双击列表项时的处理"""
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path:
            try:
                subprocess.run(["open", "-R", path])
            except Exception as e:
                self.status_label.setText(f"打开文件失败: {str(e)}")

def main():
    app = QApplication(sys.argv)
    
    # 设置应用样式
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Base, QColor(252, 252, 252))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(248, 248, 248))
    palette.setColor(QPalette.ColorRole.Text, QColor(0, 0, 0))
    palette.setColor(QPalette.ColorRole.Window, QColor(236, 236, 236))
    app.setPalette(palette)
    
    window = SearchWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 