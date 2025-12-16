import os
import sys
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from tkinter import Label, Scrollbar

# 获取程序所在目录
base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# 确保PIL库被正确导入
Image = None
ImageTk = None
try:
    from PIL import Image, ImageTk
except ImportError:
    # 如果导入失败，记录错误到当前工作目录
    error_log_path = os.path.join(os.getcwd(), 'pil_import_error.log')
    with open(error_log_path, 'w') as f:
        f.write('Failed to import PIL library')

class AboutWindow:
    def __init__(self):
        try:
            # 创建主窗口
            self.root = ttk.Window(title="关于智能Hosts测速工具", themename="darkly")
            self.root.resizable(False, False)
            # 增加窗口宽度以显示完整GitHub链接
            self.window_width = 750
            self.window_height = 450
            self.expanded_height = 700  # 展开使用说明时的窗口高度
            self.root.geometry("{}x{}+{}+{}".format(
                self.window_width,
                self.window_height,
                int(self.root.winfo_screenwidth() / 2 - self.window_width / 2),
                int(self.root.winfo_screenheight() / 2 - self.window_height / 2)
            ))
            
            # 初始化变量
            self.usage_expanded = False
            self.usage_frame = None
            
            # 创建界面
            self.create_widgets()
            
            # 运行主循环
            self.root.mainloop()
        except Exception as e:
            import traceback
            with open("about_error.log", "w") as f:
                f.write(f"初始化错误: {e}\n")
                f.write(traceback.format_exc())
            raise
    
    def create_widgets(self):
        # 设置root的grid布局
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_rowconfigure(1, minsize=80)  # 为按钮区域设置最小高度
        self.root.grid_columnconfigure(0, weight=1)
        
        # 创建主框架
        main_frame = ttk.Frame(self.root, padding=20)
        main_frame.grid(row=0, column=0, sticky="nsew")
        main_frame.grid_rowconfigure(0, weight=1)
        main_frame.grid_columnconfigure(1, weight=1)
        
        # 左侧头像区域
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="n", padx=(0, 20))
        
        # 加载头像图片
        self.load_avatar(left_frame)
        
        # 右侧信息区域
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew")
        
        # 底部按钮区域
        button_frame = ttk.Frame(self.root, padding=(20, 0, 20, 20))
        button_frame.grid(row=1, column=0, sticky="ew")
        
        # 软件名称和版本
        name_label = ttk.Label(right_frame, text="智能Hosts测速工具", font= ("微软雅黑", 18, "bold"))
        name_label.pack(pady=(0, 5), anchor="w")
        
        version_label = ttk.Label(right_frame, text="V1.0", font= ("微软雅黑", 12))
        version_label.pack(pady=(0, 15), anchor="w")
        
        # 软件描述
        desc_label = ttk.Label(right_frame, text="一个智能获取域名ip进行测试写入hosts文件的工具", 
                             font= ("微软雅黑", 10), wraplength=450, justify="left")
        desc_label.pack(pady=(0, 20), anchor="w")
        
        # 作者信息
        author_label = ttk.Label(right_frame, text="作者：毕加索自画像", 
                               font= ("微软雅黑", 10))
        author_label.pack(pady=(0, 5), anchor="w")
        
        # GitHub链接 - 单独一行显示，确保完整显示
        github_link = Label(right_frame, text="github主页：https://github.com/KenDvD", 
                          font= ("微软雅黑", 10, "underline"), fg="blue", cursor="hand2")
        github_link.pack(pady=(0, 15), anchor="w")
        github_link.bind("<Button-1>", lambda e: self.open_github_link())
        
        # 开源提示（红色警告框）
        warning_frame = ttk.Frame(right_frame)
        warning_frame.pack(pady=(20, 0), fill=X, anchor="w")
        
        warning_label = Label(warning_frame, text="该工具完全开源免费！如果你买到此软件那么你被坑了", 
                                font= ("微软雅黑", 10, "bold"), foreground="white",
                                background="red", wraplength=450, justify="left")
        warning_label.pack(fill=X, expand=True, padx=10, pady=10)
        
        # 详细使用说明按钮 - 使用更明显的样式
        usage_btn = ttk.Button(button_frame, text="详细使用说明", 
                             command=self.toggle_usage, bootstyle=SUCCESS, width=15)
        usage_btn.pack(side=LEFT, padx=(0, 10))
        
        # 关闭按钮
        close_btn = ttk.Button(button_frame, text="确定", 
                             command=self.root.destroy, bootstyle=PRIMARY, width=10)
        close_btn.pack(side=RIGHT)
    
    def load_avatar(self, parent_frame):
        """加载头像图片 - 简化版"""
        # 简化头像加载逻辑，直接使用base_path
        avatar_path = os.path.join(base_path, "头像.jpg")
        
        # 尝试直接使用PIL加载图片
        try:
            from PIL import Image, ImageTk
            image = Image.open(avatar_path)
            image = image.resize((150, 150), Image.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            
            # 显示头像
            avatar_label = ttk.Label(parent_frame, image=photo)
            avatar_label.image = photo  # 保持引用
            avatar_label.pack()
        except Exception as e:
            # 加载失败时显示占位符，并打印错误信息到控制台
            import traceback
            print(f"加载头像失败: {e}")
            print(traceback.format_exc())
            
            avatar_label = ttk.Label(parent_frame, text="🤖", font= ("微软雅黑", 80))
            avatar_label.pack()
    
    def open_github_link(self):
        """打开GitHub链接"""
        import webbrowser
        webbrowser.open("https://github.com/KenDvD")
    
    def toggle_usage(self):
        """切换使用说明展开/收起"""
        if not self.usage_expanded:
            # 创建使用说明框架
            if self.usage_frame is None:
                # 获取右侧信息框架
                main_frame = self.root.winfo_children()[0]  # main_frame是root的第一个子组件
                right_frame = main_frame.winfo_children()[1]  # right_frame是main_frame的第二个子组件
                
                self.usage_frame = ttk.LabelFrame(right_frame, text="软件详细使用说明", 
                                                padding=20)
                self.usage_frame.pack(fill=X, padx=0, pady=(10, 0), anchor="w")
                
                # 使用说明内容
                usage_content = """
软件详细使用说明：

1. 首先以管理员身份打开软件，点击--自定义网站预设--选择你需要测速的域名（可以自己添加自己想要的域名）

2. 例如github这个网址单击选择后，点击智能解析ip也可以再点击刷新远程Hosts可以获取更多IP
   （刷新远程hosts是github专属的，其他域名均是智能解析IP后测速。）

3. 点击开始测速---选择延迟低的ip写入你的hosts，也可以点击一键添加延迟最低的IP

---其他功能---

1. 刷新DNS：清除DNS缓存，使Hosts文件的修改立即生效

2. 查看hosts文件：以默认编辑器打开系统Hosts文件

3. 添加/删除预设：管理自定义的域名列表，方便下次使用

4. 手动选择IP：可以根据实际需求选择特定IP写入Hosts文件

5. 自动排序：测速完成后，结果会按延迟时间自动排序，方便选择最优IP
                """
                
                # 使用ScrolledText组件实现滚动功能 - 增加高度以提高可读性
                usage_text = ttk.ScrolledText(self.usage_frame, wrap=WORD, font=("微软雅黑", 10), height=15)
                usage_text.insert("1.0", usage_content.strip())
                usage_text.config(state="disabled")  # 设置为只读
                usage_text.pack(fill=X, anchor="w")
            else:
                self.usage_frame.pack(fill=X, padx=0, pady=(10, 0), anchor="w")
            
            self.usage_expanded = True
            # 调整窗口大小以适应内容 - 使用正确的窗口宽度和更大的高度
            self.root.geometry("{}x{}".format(self.window_width, self.expanded_height))
        else:
            # 隐藏使用说明
            if self.usage_frame:
                self.usage_frame.pack_forget()
            
            self.usage_expanded = False
            # 恢复窗口原始大小 - 使用正确的窗口尺寸变量
            self.root.geometry("{}x{}".format(self.window_width, self.window_height))

if __name__ == "__main__":
    # 直接运行，不需要管理员权限检查
    AboutWindow()