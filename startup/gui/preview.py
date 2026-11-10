"""Local design preview. Never reads saved keys or connects to the lab."""
import app


if __name__ == "__main__":
    class PreviewProc:
        def __init__(self, *args, **kwargs):
            pass

        def start(self):
            pass

        def kill(self):
            pass

        def is_running(self):
            return False

    app.Proc = PreviewProc
    app.load_config = lambda: None
    app.load_notes = lambda: None
    app.save_config = lambda: None
    app.save_notes = lambda text: None
    window = app.App()
    window.title("PurpleAI Control · local preview")
    window.mainloop()
