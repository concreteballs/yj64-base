package org.blackmirror.blackmirror;

import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
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
    private static final int PICK_CONFIG_FILE = 4101;

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

        Button config = new Button(this);
        config.setText("Import LLM config file");
        config.setOnClickListener(v -> pickConfigFile());
        root.addView(config);

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
        crash.setText("Check last Base App crash");
        crash.setOnClickListener(v -> checkLastCrashAndCopy());
        root.addView(crash);

        Button allTests = new Button(this);
        allTests.setText("TEST ALL FUNCTIONS + COPY REPORT");
        allTests.setOnClickListener(v -> requestFullTest());
        root.addView(allTests);

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

    private void pickConfigFile() {
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("application/json");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION
            | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(intent, PICK_CONFIG_FILE);
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != PICK_CONFIG_FILE || resultCode != RESULT_OK
                || data == null || data.getData() == null) return;
        Uri uri = data.getData();
        try {
            File target = new File(getFilesDir(), "yj64-llm-config.json");
            try (InputStream in = getContentResolver().openInputStream(uri);
                 FileOutputStream out = new FileOutputStream(target, false)) {
                if (in == null) throw new IOException("Unable to open selected document");
                byte[] buffer = new byte[8192];
                int count;
                while ((count = in.read(buffer)) != -1) out.write(buffer, 0, count);
                out.flush();
                out.getFD().sync();
            }
            append("llm_config_file_imported", "{}");
            status.setText(identityText() + "\n\nLLM config file imported.");
            Toast.makeText(this, "LLM config imported", Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            append("llm_config_file_import_failed",
                "{"error_type":"" + escape(e.getClass().getSimpleName()) + ""}");
            Toast.makeText(this, "Import failed: " + e, Toast.LENGTH_LONG).show();
        }
    }

    private void checkLastCrashAndCopy() {
        append("last_crash_check_started", "{}");
        String result = lastExitReport();
        append("last_crash_check_completed",
            "{"report":"" + escape(result) + ""}");
        copyText(result + "\n\n--- YJ-64 REPORT ---\n" + readReport());
        status.setText(result);
        Toast.makeText(this, "Crash report copied", Toast.LENGTH_SHORT).show();
    }

    private String lastExitReport() {
        if (android.os.Build.VERSION.SDK_INT < 30) {
            return "ApplicationExitInfo unavailable below Android 11.";
        }
        ActivityManager am = (ActivityManager) getSystemService(ACTIVITY_SERVICE);
        java.util.List<ApplicationExitInfo> exits =
            am.getHistoricalProcessExitReasons(getPackageName(), 0, 10);
        if (exits == null || exits.isEmpty()) return "No historical Base App exits reported.";
        StringBuilder out = new StringBuilder("YJ-64 LAST BASE APP EXIT(S)\n");
        for (ApplicationExitInfo info : exits) {
            out.append("time_ms=").append(info.getTimestamp())
                .append(", reason=").append(reasonName(info.getReason()))
                .append(", status=").append(info.getStatus())
                .append(", pid=").append(info.getPid()).append("\n");
            if (info.getDescription() != null) {
                out.append("description=").append(info.getDescription()).append("\n");
            }
        }
        return out.toString().trim();
    }

    private String reasonName(int reason) {
        switch (reason) {
            case ApplicationExitInfo.REASON_CRASH: return "CRASH";
            case ApplicationExitInfo.REASON_ANR: return "ANR";
            case ApplicationExitInfo.REASON_LOW_MEMORY: return "LOW_MEMORY";
            case ApplicationExitInfo.REASON_USER_REQUESTED: return "USER_REQUESTED";
            case ApplicationExitInfo.REASON_SIGNALED: return "SIGNALED";
            case ApplicationExitInfo.REASON_INITIALIZATION_FAILURE: return "INITIALIZATION_FAILURE";
            case ApplicationExitInfo.REASON_PERMISSION_CHANGE: return "PERMISSION_CHANGE";
            case ApplicationExitInfo.REASON_EXCESSIVE_RESOURCE_USAGE: return "EXCESSIVE_RESOURCE_USAGE";
            default: return "REASON_" + reason;
        }
    }

    private void requestFullTest() {
        final String testId = UUID.randomUUID().toString().replace("-", "");
        File command = new File(getFilesDir(), "yj64-test-command.json");
        File result = new File(getFilesDir(), "yj64-test-result.json");
        try {
            if (result.exists()) result.delete();
            String json = "{"action":"full_test","test_id":"" + testId + ""}";
            try (FileOutputStream out = new FileOutputStream(command, false)) {
                out.write(json.getBytes(StandardCharsets.UTF_8));
                out.flush();
                out.getFD().sync();
            }
            append("full_test_requested", "{"test_id":"" + testId + ""}");
            status.setText(identityText() + "\n\nFull function test requested...");
            new Thread(() -> waitForFullTest(testId)).start();
        } catch (IOException e) {
            Toast.makeText(this, "Full test request failed: " + e, Toast.LENGTH_LONG).show();
        }
    }

    private void waitForFullTest(String testId) {
        long deadline = System.currentTimeMillis() + 120000L;
        while (System.currentTimeMillis() < deadline) {
            File result = new File(getFilesDir(), "yj64-test-result.json");
            if (result.isFile()) {
                try {
                    String text = readFile(result);
                    if (text.contains("\"test_id\":\"" + testId + "\"")) {
                        String report = readReport();
                        append("full_test_result_collected",
                            "{"test_id":"" + testId + ""}");
                        runOnUiThread(() -> {
                            copyText(report);
                            status.setText(report);
                            Toast.makeText(this, "Full test report copied", Toast.LENGTH_SHORT).show();
                        });
                        return;
                    }
                } catch (Exception ignored) {}
            }
            try { Thread.sleep(500); }
            catch (InterruptedException e) { Thread.currentThread().interrupt(); return; }
        }
        runOnUiThread(() -> Toast.makeText(
            this, "Full test timed out; copy report manually.", Toast.LENGTH_LONG).show());
    }

    private String readReport() {
        File file = reportFile();
        return file.exists() ? readFile(file) : "Report file does not exist.";
    }

    private String readFile(File file) {
        StringBuilder text = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new FileReader(file))) {
            String line;
            while ((line = reader.readLine()) != null) text.append(line).append('\n');
        } catch (IOException e) {
            return "Read failed: " + e;
        }
        return text.toString();
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
