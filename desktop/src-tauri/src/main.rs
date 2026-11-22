// Deep Study Center desktop shell (SPEC §25).
// Starts the bundled Python backend (`dsc-backend serve`) on a free local port, shows a "starting" page, switches the
// window to the app when the backend answers, and stops the backend when the app exits. The learner's data stays in
// the normal workspace (~/DeepStudy, or DSC_WORKSPACE); backend output goes to the app's log folder.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{self, File};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, Url};

struct Backend(Mutex<Option<Child>>);

fn free_port() -> std::io::Result<u16> {
    Ok(TcpListener::bind("127.0.0.1:0")?.local_addr()?.port())
}

fn backend_exe(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().resource_dir().map_err(|e| e.to_string())?;
    let exe = dir.join("backend").join(if cfg!(windows) { "dsc-backend.exe" } else { "dsc-backend" });
    if exe.exists() { Ok(exe) } else { Err(format!("The backend is missing: {}", exe.display())) }
}

fn start_backend(app: &tauri::AppHandle, port: u16) -> Result<Child, String> {
    let exe = backend_exe(app)?;
    let logs = app.path().app_log_dir().map_err(|e| e.to_string())?;
    fs::create_dir_all(&logs).map_err(|e| e.to_string())?;
    let log = File::create(logs.join("backend.log")).map_err(|e| e.to_string())?;
    let mut cmd = Command::new(&exe);
    cmd.args(["serve", "--port", &port.to_string()])
        .current_dir(exe.parent().unwrap_or(&exe))
        .env("PYTHONUNBUFFERED", "1") // the log file gets every line at once, also when the app stops the backend
        .stdin(Stdio::null())
        .stdout(Stdio::from(log.try_clone().map_err(|e| e.to_string())?))
        .stderr(Stdio::from(log));
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW: no console window for the backend
    }
    cmd.spawn().map_err(|e| format!("Could not start the backend: {e}"))
}

fn wait_until_listening(port: u16, timeout: Duration) -> bool {
    let start = Instant::now();
    while start.elapsed() < timeout {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(200));
    }
    false
}

fn show_error(app: &tauri::AppHandle, msg: &str) {
    if let Some(win) = app.get_webview_window("main") {
        let js = format!("window.showError({})", serde_json_string(msg));
        let _ = win.eval(&js);
    }
}

// A JSON string literal (no serde dependency needed for one string).
fn serde_json_string(s: &str) -> String {
    let mut out = String::from("\"");
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            c if (c as u32) < 0x20 => out.push_str(&format!("\\u{:04x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

fn stop_backend(app: &tauri::AppHandle) {
    if let Some(state) = app.try_state::<Backend>() {
        if let Ok(mut guard) = state.0.lock() {
            if let Some(mut child) = guard.take() {
                let _ = child.kill();
                let _ = child.wait();
            }
        }
    }
}

fn main() {
    let app = tauri::Builder::default()
        .setup(|app| {
            app.manage(Backend(Mutex::new(None)));
            let handle = app.handle().clone();
            thread::spawn(move || {
                let port = match free_port() {
                    Ok(p) => p,
                    Err(e) => return show_error(&handle, &format!("No free local port: {e}")),
                };
                match start_backend(&handle, port) {
                    Ok(child) => {
                        if let Ok(mut guard) = handle.state::<Backend>().0.lock() {
                            *guard = Some(child);
                        }
                    }
                    Err(e) => return show_error(&handle, &e),
                }
                if !wait_until_listening(port, Duration::from_secs(90)) {
                    let log = handle.path().app_log_dir().map(|d| d.join("backend.log").display().to_string()).unwrap_or_default();
                    return show_error(&handle, &format!("The backend did not answer within 90 seconds.\nLog: {log}"));
                }
                if let (Some(win), Ok(url)) = (handle.get_webview_window("main"), Url::parse(&format!("http://127.0.0.1:{port}/"))) {
                    let _ = win.navigate(url);
                }
            });
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Deep Study Center app");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            stop_backend(handle);
        }
    });
}
