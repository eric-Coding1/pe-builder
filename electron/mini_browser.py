"""
PE Builder Mini Browser — 适用于 Windows PE 的简易浏览器
使用 WebView2 渲染，带基本导航功能
"""
import os
import sys
import webview

WINDOW_TITLE = 'PE Browser 简易浏览器'


class BrowserApi:
    def go_back(self):
        try:
            webview.windows[0].evaluate_js('history.back()')
        except:
            pass
    
    def go_forward(self):
        try:
            webview.windows[0].evaluate_js('history.forward()')
        except:
            pass
    
    def get_default_home(self):
        return 'https://www.baidu.com'


def main():
    home_url = 'https://www.baidu.com'
    if len(sys.argv) > 1:
        home_url = sys.argv[1]
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family: "Segoe UI", "Microsoft YaHei", sans-serif; overflow:hidden; }}
  
  #toolbar {{
    display: flex; align-items: center; gap: 4px;
    padding: 4px 8px;
    background: #1a1d24; color: #e8eaed;
    border-bottom: 1px solid #3a4050;
    user-select: none;
  }}
  
  .nav-btn {{
    background: none; border: none; color: #9aa0a8;
    width: 32px; height: 32px; border-radius: 4px;
    cursor: pointer; font-size: 16px;
    display: flex; align-items: center; justify-content: center;
    transition: all .15s;
  }}
  .nav-btn:hover {{ background: #323844; color: #e8eaed; }}
  .nav-btn:active {{ background: #3a4050; }}
  
  #url-bar {{
    flex: 1; margin: 0 8px;
    padding: 6px 12px;
    background: #2a2f3a; border: 1px solid #3a4050;
    border-radius: 16px; color: #e8eaed;
    font-size: 13px; outline: none;
    transition: border .2s;
  }}
  #url-bar:focus {{ border-color: #4a9eff; }}
  
  #go-btn {{
    background: #4a9eff; border: none;
    color: #fff; font-weight: 600;
    padding: 6px 16px; border-radius: 16px;
    cursor: pointer; font-size: 13px;
    transition: background .2s;
  }}
  #go-btn:hover {{ background: #3a8aee; }}

  #status {{
    padding: 2px 12px;
    font-size: 11px; color: #6b7280;
    background: #22262f; border-top: 1px solid #3a4050;
    display: flex; align-items: center;
    height: 24px;
  }}
  
  iframe {{
    width: 100%; border: none;
    height: calc(100vh - 60px);
  }}

  .loading #go-btn {{ opacity: 0.6; }}
</style>
</head>
<body>
<div id="toolbar">
  <button class="nav-btn" onclick="history.back()" title="后退">&#x25C0;</button>
  <button class="nav-btn" onclick="history.forward()" title="前进">&#x25B6;</button>
  <button class="nav-btn" onclick="location.reload()" title="刷新">&#x21BB;</button>
  <input id="url-bar" type="text" placeholder="输入网址..."
    onkeydown="if(event.key==='Enter')navigate()"
    value="{home_url}">
  <button id="go-btn" onclick="navigate()">GO</button>
</div>
<iframe id="browser-frame" src="{home_url}"></iframe>
<div id="status">就绪 | PE Browser v1.0 | 基于 Edge WebView2</div>

<script>
function navigate() {{
  var url = document.getElementById('url-bar').value.trim();
  if (!url.startsWith('http://') && !url.startsWith('https://')) {{
    url = 'https://' + url;
  }}
  document.getElementById('browser-frame').src = url;
  document.getElementById('url-bar').value = url;
}}

// Update URL bar when navigating
document.getElementById('browser-frame').addEventListener('load', function() {{
  try {{
    document.getElementById('url-bar').value = this.contentWindow.location.href;
  }} catch(e) {{}}
}});
</script>
</body>
</html>
'''
    
    # Write HTML to temp
    import tempfile
    html_path = os.path.join(tempfile.gettempdir(), 'pe_browser.html')
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    window = webview.create_window(
        title=WINDOW_TITLE,
        url=html_path,
        width=1024,
        height=700,
        min_size=(640, 480),
        resizable=True,
        text_select=True,
        background_color='#1a1d24',
    )
    webview.start(debug=False, http_server=True)


if __name__ == '__main__':
    main()
