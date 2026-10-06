package org.blackmirror.blackmirror;

import android.app.Activity;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.os.Bundle;
import android.os.Process;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.UUID;

public class MonitorActivity extends Activity {
    private static final String REPORT = "yj64-reports/yj64-report.jsonl";
    private static final String PID_FILE = "yj64-main-process.pid";
    private TextView status;

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        append("monitor_window_opened", identityJson());

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(32, 32, 32, 32);

        TextView title = new TextView(this);
        title.setText("YJ-64 Internal Monitor");
        title.setTextSize(24);
        root.addView(title, new LinearLayout.LayoutParams(-1, 80));

        status = new TextView(this);
        status.setText(identityText());
        status.setTextIsSelectable(true);
        root.addView(status, new LinearLayout.LayoutParams(-1, 0, 1));

        Button refresh = new Button(this);
        refresh.setText("Refresh monitor status");
        refresh.setOnClickListener(v -> {
            status.setText(identityText());
            append("monitor_status_refreshed", identityJson());
        });
        root.addView(refresh);

        Button copy = new Button(this);
        copy.setText("Copy report");
        copy.setOnClickListener(v -> copyReport());
        root.addView(copy);

        Button paths = new Button(this);
        paths.setText("Copy report paths");
        paths.setOnClickListener(v -> copyPaths());
        root.addView(paths);

        Button crash = new Button(this);
        crash.setText("TEST: crash Base App process");
        crash.setOnClickListener(v -> crashBaseProcess());
        root.addView(crash);

        ScrollView scroll = new ScrollView(this);
        scroll.addView(root);
        setContentView(scroll);
    }

    private File reportFile() { return new File(getFilesDir(), REPORT); }
    private File pidFile() { return new File(getFilesDir(), PID_FILE); }

    private String identityText() {
        return "MONITOR ALIVE\n"
            + "PID: " + Process.myPid() + "\n"
            + "UID: " + Process.myUid() + "\n"
            + "Process: " + Process.myProcessName() + "\n\n"
            + "Report:\n" + reportFile().getAbsolutePath() + "\n\n"
            + "Archive:\n" + new File(getFilesDir(),
                "yj64-reports/yj64-diagnostics.zip").getAbsolutePath();
    }

    private String identityJson() {
        return "{\"pid\":" + Process.myPid()
            + ",\"uid\":" + Process.myUid()
            + ",\"process_name\":\"" + escape(Process.myProcessName()) + "\"}";
    }

    private void copyPaths() {
        copyText(reportFile().getAbsolutePath() + "\n"
            + new File(getFilesDir(), "yj64-reports/yj64-diagnostics.zip").getAbsolutePath());
        Toast.makeText(this, "Report paths copied", Toast.LENGTH_SHORT).show();
    }

    private void copyReport() {
        File file = reportFile();
        if (!file.exists()) {
            Toast.makeText(this, "Report file does not exist yet", Toast.LENGTH_SHORT).show();
            return;
        }
        StringBuilder text = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) text.append(line).append('\n');
        } catch (IOException e) {
            Toast.makeText(this, "Report read failed: " + e, Toast.LENGTH_LONG).show();
            return;
        }
        copyText(text.toString());
        Toast.makeText(this, "Report copied", Toast.LENGTH_SHORT).show();
    }

    private void copyText(String text) {
        ClipboardManager clipboard =
            (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
        clipboard.setPrimaryClip(ClipData.newPlainText("YJ-64", text));
    }

    private void crashBaseProcess() {
        int pid = readMainPid();
        append("main_process_crash_requested",
            "{\"target_pid\":" + pid
            + ",\"monitor_pid\":" + Process.myPid()
            + ",\"monitor_process_name\":\"" + escape(Process.myProcessName()) + "\"}");

        if (pid <= 0 || pid == Process.myPid()) {
            Toast.makeText(this, "Invalid Base App PID: " + pid, Toast.LENGTH_LONG).show();
            return;
        }

        Toast.makeText(this, "Crashing Base App PID " + pid, Toast.LENGTH_SHORT).show();
        new Thread(() -> {
            try { Thread.sleep(250); }
            catch (InterruptedException ignored) { Thread.currentThread().interrupt(); }
            Process.killProcess(pid);
            runOnUiThread(() -> status.setText(identityText()
                + "\n\nBASE APP PROCESS WAS KILLED."
                + "\nMONITOR PROCESS IS STILL ALIVE."));
        }).start();
    }

    private int readMainPid() {
        try (BufferedReader reader = new BufferedReader(new FileReader(pidFile()))) {
            return Integer.parseInt(reader.readLine().trim());
        } catch (Exception e) { return -1; }
    }

    private void append(String event, String data) {
        File file = reportFile();
        File parent = file.getParentFile();
        if (parent != null) parent.mkdirs();
        String line = "{\"schema\":\"yj64.diagnostic.v1\","
            + "\"agent\":\"yj64-internal-monitor\","
            + "\"event\":\"" + escape(event) + "\","
            + "\"timestamp_ms\":" + System.currentTimeMillis() + ","
            + "\"message_id\":\"MON-" + UUID.randomUUID().toString().replace("-", "") + "\","
            + "\"data\":" + data + "}\n";
        try (FileOutputStream out = new FileOutputStream(file, true)) {
            out.write(line.getBytes(StandardCharsets.UTF_8));
            out.flush();
            out.getFD().sync();
        } catch (IOException ignored) {}
    }

    private String escape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
