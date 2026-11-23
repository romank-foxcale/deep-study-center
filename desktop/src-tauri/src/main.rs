// Deep Study Center desktop shell (SPEC §25).
// Starts the bundled Python backend (`dsc-backend serve`) on a free local port, shows a "starting" page, switches the
// window to the app when the backend answers, and stops the backend when the app exits. The learner's data stays in
// the normal workspace (~/DeepStudy, or DSC_WORKSPACE); backend output goes to the app's log folder.
// Updates (SPEC §39): after the start, the app asks GitHub Releases for a newer signed version and offers to install it.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::fs::{self, File};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, Url};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_updater::UpdaterExt;

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
        let js = format!("window.showError({})", serde_json::Value::from(msg));
        let _ = win.eval(&js);
    }
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

// One line in the app's log folder (update.log), so a failed check can be found without a console.
fn log_update(app: &tauri::AppHandle, msg: &str) {
    if let Ok(dir) = app.path().app_log_dir() {
        let _ = fs::create_dir_all(&dir);
        if let Ok(mut f) = fs::OpenOptions::new().create(true).append(true).open(dir.join("update.log")) {
            use std::io::Write;
            let secs = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
            let _ = writeln!(f, "{secs} {msg}");
        }
    }
}

// Ask the update server for a newer version. If there is one, offer it; on "Install", download it, stop the backend
// (its files are replaced), and run the installer, which closes the app and opens the new version.
// DSC_UPDATE_URL replaces the server (for a test); DSC_NO_UPDATE_CHECK=1 turns the check off.
fn check_for_update(app: &tauri::AppHandle) -> Result<(), String> {
    if std::env::var("DSC_NO_UPDATE_CHECK").map(|v| v == "1").unwrap_or(false) {
        return Ok(log_update(app, "check turned off (DSC_NO_UPDATE_CHECK=1)"));
    }
    let mut builder = app.updater_builder().timeout(Duration::from_secs(30));
    if let Ok(url) = std::env::var("DSC_UPDATE_URL") {
        let url = Url::parse(&url).map_err(|e| format!("DSC_UPDATE_URL: {e}"))?;
        builder = builder.endpoints(vec![url]).map_err(|e| e.to_string())?;
    }
    let updater = builder.build().map_err(|e| e.to_string())?;
    let update = match tauri::async_runtime::block_on(updater.check()).map_err(|e| e.to_string())? {
        Some(u) => u,
        None => return Ok(log_update(app, "no newer version")),
    };
    log_update(app, &format!("version {} found (this is {})", update.version, update.current_version));
    let yes = app.dialog()
        .message(format!("Deep Study Center {} is ready to install. You have {}.\n\nThe app closes, installs the new \
            version and opens again. Your workspace is not changed. What is new: the Releases page on GitHub.",
            update.version, update.current_version))
        .title("A new version")
        .kind(MessageDialogKind::Info)
        .buttons(MessageDialogButtons::OkCancelCustom("Install and restart".into(), "Later".into()))
        .blocking_show();
    if !yes {
        return Ok(log_update(app, "the learner chose Later"));
    }
    let bytes = tauri::async_runtime::block_on(update.download(|_, _| {}, || {})).map_err(|e| format!("download: {e}"))?;
    log_update(app, &format!("downloaded {} bytes, signature checked; installing", bytes.len()));
    stop_backend(app);
    update.install(bytes).map_err(|e| format!("install: {e}"))  // on Windows this exits the app
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
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
                if !cfg!(debug_assertions) {
                    let h = handle.clone();
                    thread::spawn(move || {
                        if let Err(e) = check_for_update(&h) {
                            log_update(&h, &format!("failed: {e}"));
                            if e.starts_with("download") || e.starts_with("install") {
                                h.dialog().message(format!("The update could not be installed.\n{e}\n\nDownload it from the Releases page on GitHub."))
                                    .title("Update failed").kind(MessageDialogKind::Error).blocking_show();
                            }
                        }
                    });
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
