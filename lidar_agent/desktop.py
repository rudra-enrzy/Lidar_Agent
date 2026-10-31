"""Desktop window for the Line Clearance Agent.

Starts the same local server as the browser app (python -m lidar_agent.app) on a free port and shows it in a native window
(pywebview: Edge WebView2 on Windows). Closing the window stops everything. Without pywebview it falls back to the
default browser, so `python -m lidar_agent.desktop` always does something useful.
"""
import functools, os, socket, socketserver, threading, webbrowser

TITLE = "Line Clearance Agent"


def _free_port(preferred=8765):
    for p in (preferred, 0):
        s = socket.socket()
        try:
            s.bind(("127.0.0.1", p)); return s.getsockname()[1]
        except OSError:
            continue
        finally:
            s.close()


def _icon():
    here = os.path.dirname(os.path.abspath(__file__))
    for name in ("logo.ico", "logo.png"):
        f = os.path.join(here, "assets", name)
        if os.path.isfile(f): return f
    return None


def main():
    from . import app
    port = _free_port()
    socketserver.ThreadingTCPServer.allow_reuse_address = True
    srv = socketserver.ThreadingTCPServer(("127.0.0.1", port), functools.partial(app.H, directory=app.HERE))
    srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    try:
        import webview
    except ImportError:
        print("pywebview is not installed (pip install pywebview) - opening the browser instead:", url)
        webbrowser.open(url)
        try:
            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        return
    try:
        webview.settings["ALLOW_DOWNLOADS"] = True         # Excel / PDF / zip links save through a normal dialog
    except Exception:
        pass
    webview.create_window(TITLE, url, width=1520, height=920, min_size=(1100, 700), confirm_close=False)
    webview.start(icon=_icon())
    srv.shutdown()


if __name__ == "__main__":
    main()
