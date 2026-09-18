#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

//! Dy-Sentry Desktop (Tauri)
//!
//! 架构对齐 rust-srec：原生窗口外壳 + 内置后端。区别在于 Dy-Sentry 后端是 Python
//! （FastAPI/uvicorn），无法直接塞进 Rust in-process，因此把它作为 **sidecar**（外部二进制）
//! 启动，webview 直接加载后端提供的页面（`http://127.0.0.1:12580/manage`）。用户双击 App
//! 打开原生窗口，从不手动访问 localhost URL。
//!
//! - 启动屏（splash）等待 sidecar 端口就绪；
//! - 就绪后打开主窗口指向管理页（监控+录制核心），直播预览作为次级入口；
//! - 系统托盘、单实例、关闭最小化到托盘、退出时杀掉 sidecar（含 ffmpeg 子进程）。

use std::path::PathBuf;
use std::process::Command as StdCommand;
use std::sync::Mutex;
use std::time::Duration;

use tauri::Emitter;
use tauri::Manager;
use tauri::menu::{Menu, MenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri_plugin_shell::ShellExt;
use tauri_plugin_shell::process::CommandChild;

const BACKEND_PORT: u16 = 12580;
const BACKEND_HOST: &str = "127.0.0.1";
const BOOT_TIMEOUT: Duration = Duration::from_secs(30);

struct AppState {
    /// 打包后的 Python 后端进程（sidecar）。退出时杀掉它及其子进程树。
    sidecar: Mutex<Option<CommandChild>>,
    /// 应用数据目录：sidecar 以此为 cwd，配置/录制产物落于此。
    data_dir: PathBuf,
}

/// 异步轮询后端 TCP 端口，直到可连接或超时。
async fn wait_for_backend(timeout: Duration) -> bool {
    let deadline = tokio::time::Instant::now() + timeout;
    loop {
        if tokio::net::TcpStream::connect((BACKEND_HOST, BACKEND_PORT))
            .await
            .is_ok()
        {
            return true;
        }
        if tokio::time::Instant::now() >= deadline {
            return false;
        }
        tokio::time::sleep(Duration::from_millis(300)).await;
    }
}

/// 杀掉 sidecar 进程树（覆盖录制产生的 ffmpeg 子进程）。
fn kill_sidecar_tree(pid: u32) {
    #[cfg(target_os = "windows")]
    {
        let _ = StdCommand::new("taskkill")
            .args(["/F", "/T", "/PID", &pid.to_string()])
            .output();
    }
    #[cfg(not(target_os = "windows"))]
    {
        let _ = StdCommand::new("kill").args(["-TERM", &pid.to_string()]).output();
    }
}

#[tauri::command]
fn quit_app(app: tauri::AppHandle) {
    app.exit(0);
}

pub fn run() {
    let builder = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            if let Some(w) = app.get_webview_window("main") {
                let _ = w.unminimize();
                let _ = w.show();
                let _ = w.set_focus();
            }
        }))
        .plugin(tauri_plugin_notification::init())
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_shell::init());

    let app = builder
        .setup(|app| {
            let data_dir = app.path().app_data_dir()?;
            std::fs::create_dir_all(&data_dir)?;
            let log_dir = app.path().app_log_dir()?;
            std::fs::create_dir_all(&log_dir)?;

            app.manage(AppState {
                sidecar: Mutex::new(None),
                data_dir: data_dir.clone(),
            });

            // 启动屏：后端（sidecar）起来前先显示加载界面。
            let _ = tauri::WebviewWindowBuilder::new(
                app,
                "splash",
                tauri::WebviewUrl::App("index.html".into()),
            )
            .title("Dy-Sentry")
            .inner_size(440.0, 320.0)
            .resizable(false)
            .decorations(false)
            .center()
            .build();

            // 启动内置 Python 后端（sidecar）。cwd 设为 app data 目录，使配置与录制持久化。
            let sidecar_cmd = match app.shell().sidecar("dy-sentry") {
                Ok(c) => c,
                Err(e) => {
                    log::error!("sidecar 未配置或未找到: {e}");
                    return Err(Box::new(e));
                }
            };
            let mut sidecar_builder = sidecar_cmd.args(["--port", &BACKEND_PORT.to_string()]);
            if let Ok(cookie) = std::env::var("DY_COOKIE") {
                if !cookie.is_empty() {
                    sidecar_builder = sidecar_builder.env("DY_COOKIE", cookie);
                }
            }
            let child = sidecar_builder.cwd(&data_dir).spawn()?;
            app.state::<AppState>().sidecar.lock().unwrap().replace(child);

            // 等待后端就绪后打开主窗口（默认指向管理/监控页）。
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                let ready = wait_for_backend(BOOT_TIMEOUT).await;
                if ready {
                    if let Some(w) = app_handle.get_webview_window("main") {
                        let _ = w.show();
                        let _ = w.set_focus();
                    } else {
                        let _ = tauri::WebviewWindowBuilder::new(
                            &app_handle,
                            "main",
                            tauri::WebviewUrl::External(
                                format!("http://{BACKEND_HOST}:{BACKEND_PORT}/manage")
                                    .parse()
                                    .unwrap(),
                            ),
                        )
                        .title("Dy-Sentry")
                        .inner_size(1280.0, 900.0)
                        .min_inner_size(860.0, 600.0)
                        .build();
                    }
                } else {
                    log::error!("后端 30s 内未就绪，主窗口未打开");
                }
                if let Some(splash) = app_handle.get_webview_window("splash") {
                    let _ = splash.close();
                }
            });

            // 系统托盘
            let handle = app.handle().clone();
            let show_hide = MenuItem::new(&handle, "显示/隐藏", true, None::<&str>)?;
            let quit = MenuItem::new(&handle, "退出", true, None::<&str>)?;
            let menu = Menu::with_items(&handle, &[&show_hide, &quit])?;
            let show_hide_id = show_hide.id().clone();
            let quit_id = quit.id().clone();
            let icon = tauri::include_image!("icons/32x32.png");
            TrayIconBuilder::with_id("dy-sentry-tray")
                .icon(icon)
                .tooltip("Dy-Sentry")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(move |app: &tauri::AppHandle, event| {
                    if event.id == quit_id {
                        app.exit(0);
                    } else if event.id == show_hide_id {
                        if let Some(w) = app.get_webview_window("main") {
                            if w.is_visible().unwrap_or(false) {
                                let _ = w.hide();
                            } else {
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        }
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        if let Some(w) = tray.app_handle().get_webview_window("main") {
                            if w.is_visible().unwrap_or(false) {
                                let _ = w.hide();
                            } else {
                                let _ = w.show();
                                let _ = w.set_focus();
                            }
                        }
                    }
                })
                .build(&handle)?;

            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building Dy-Sentry desktop");

    app.run(|app_handle, event| {
        // 主窗口关闭按钮：最小化到托盘而非退出。
        if let tauri::RunEvent::WindowEvent {
            label,
            event: tauri::WindowEvent::CloseRequested { api, .. },
            ..
        } = &event
        {
            if *label == "main" {
                api.prevent_close();
                if let Some(w) = app_handle.get_webview_window("main") {
                    let _ = w.hide();
                }
                return;
            }
        }

        // 优雅退出：杀掉后端 sidecar（含 ffmpeg 子进程树）。
        if matches!(
            event,
            tauri::RunEvent::ExitRequested { .. } | tauri::RunEvent::Exit
        ) {
            if let Some(state) = app_handle.try_state::<AppState>() {
                if let Some(child) = state.sidecar.lock().unwrap().take() {
                    let pid = child.pid();
                    let _ = child.kill();
                    kill_sidecar_tree(pid);
                }
            }
        }
    });
}
