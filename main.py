import sys
import traceback
from pathlib import Path


def crash_report(info):
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent
    try:
        (base / "DownloadBro_ошибка.txt").write_text(info, encoding="utf-8")
    except OSError:
        pass


def main():
    from downloadbro.app import App
    from downloadbro.settings import Settings, acquire_single_instance, focus_existing_window

    if not acquire_single_instance():
        import tkinter as tk
        from tkinter import messagebox

        if not focus_existing_window():
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("DownloadBro", "Окно уже открыто — смотрите на панели задач.")
            root.destroy()
        return

    app = App(Settings())
    app.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        info = traceback.format_exc()
        crash_report(info)
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("DownloadBro — сбой", f"{info[-1200:]}\n\nПодробности: DownloadBro_ошибка.txt")
            root.destroy()
        except Exception:
            pass
        if sys.stderr:
            print(info, file=sys.stderr)
        sys.exit(1)
