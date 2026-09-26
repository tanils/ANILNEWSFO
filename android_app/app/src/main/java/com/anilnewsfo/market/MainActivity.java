package com.anilnewsfo.market;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Typeface;
import android.view.Gravity;
import android.view.View;
import android.widget.*;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private static final String FEED_URL =
        "https://raw.githubusercontent.com/tanils/ANILNEWSFO/main/data/app_feed.json";

    private LinearLayout content;
    private TextView status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildUi();
        loadFeed();
    }

    private void buildUi() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(24, 20, 24, 12);

        TextView title = new TextView(this);
        title.setText("ANILNEWSFO");
        title.setTextSize(26);
        title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        root.addView(title);

        status = new TextView(this);
        status.setText("Loading latest market intelligence…");
        status.setTextSize(13);
        root.addView(status);

        LinearLayout tabs = new LinearLayout(this);
        tabs.setOrientation(LinearLayout.HORIZONTAL);

        Button news = tabButton("📰 NEWS");
        Button fno = tabButton("📊 F&O");
        Button breakout = tabButton("🔥 BREAKOUTS");
        Button refresh = tabButton("↻");

        tabs.addView(news, new LinearLayout.LayoutParams(0, 56, 1));
        tabs.addView(fno, new LinearLayout.LayoutParams(0, 56, 1));
        tabs.addView(breakout, new LinearLayout.LayoutParams(0, 56, 1));
        tabs.addView(refresh, new LinearLayout.LayoutParams(56, 56));

        root.addView(tabs);

        ScrollView scroll = new ScrollView(this);
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        scroll.addView(content);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));

        news.setOnClickListener(v -> loadSection("news"));
        fno.setOnClickListener(v -> loadSection("fno"));
        breakout.setOnClickListener(v -> loadSection("breakouts"));
        refresh.setOnClickListener(v -> loadFeed());

        setContentView(root);
    }

    private Button tabButton(String text) {
        Button b = new Button(this);
        b.setText(text);
        b.setTextSize(11);
        return b;
    }

    private JSONObject latest;

    private void loadFeed() {
        status.setText("Refreshing latest pipeline output…");
        new Thread(() -> {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(FEED_URL).openConnection();
                c.setConnectTimeout(10000);
                c.setReadTimeout(15000);
                c.setRequestMethod("GET");
                StringBuilder out = new StringBuilder();
                try (BufferedReader r = new BufferedReader(new InputStreamReader(c.getInputStream()))) {
                    String line;
                    while ((line = r.readLine()) != null) out.append(line);
                }
                c.disconnect();
                latest = new JSONObject(out.toString());
                runOnUiThread(() -> {
                    status.setText("Updated: " + latest.optString("generated_at_utc", "unknown"));
                    loadSection("news");
                });
            } catch (Exception e) {
                runOnUiThread(() -> {
                    status.setText("Feed unavailable. Pull to retry.");
                    showMessage("Unable to load latest pipeline data.\n" + e.getMessage());
                });
            }
        }).start();
    }

    private void clear() {
        content.removeAllViews();
    }

    private void heading(String text) {
        TextView h = new TextView(this);
        h.setText(text);
        h.setTextSize(20);
        h.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        h.setPadding(0, 20, 0, 10);
        content.addView(h);
    }

    private void card(String text) {
        TextView v = new TextView(this);
        v.setText(text);
        v.setTextSize(15);
        v.setPadding(18, 18, 18, 18);
        v.setBackgroundResource(android.R.drawable.dialog_holo_light_frame);
        LinearLayout.LayoutParams p = new LinearLayout.LayoutParams(-1, -2);
        p.setMargins(0, 0, 0, 12);
        content.addView(v, p);
    }

    private void loadSection(String section) {
        clear();
        if (latest == null) {
            showMessage("No feed loaded yet.");
            return;
        }

        if ("news".equals(section)) {
            heading("📰 NEWS / MARKET BLOG");
            JSONArray news = latest.optJSONArray("news");
            if (news == null || news.length() == 0) {
                card("No current/recent news in this pipeline run.");
                return;
            }
            for (int i = 0; i < news.length(); i++) {
                JSONObject n = news.optJSONObject(i);
                if (n == null) continue;
                String symbols = n.optString("symbols", "MARKET");
                card(
                    symbols + "\n\n" +
                    n.optString("headline", "") + "\n\n" +
                    "Type: " + n.optString("news_type", "context") +
                    " | Freshness: " + n.optString("freshness", "unknown") + "\n" +
                    "Source: " + n.optString("source", "unknown") + "\n" +
                    "Published: " + n.optString("published", "unknown") + "\n\n" +
                    n.optString("summary", "")
                );
            }
        } else if ("fno".equals(section)) {
            heading("📊 F&O / OPTIONS");
            JSONArray fno = latest.optJSONArray("fno_candidates");
            if (fno == null || fno.length() == 0) {
                card("No F&O candidates were produced.");
                return;
            }
            for (int i = 0; i < fno.length(); i++) {
                JSONObject x = fno.optJSONObject(i);
                if (x == null) continue;
                String chain = x.optBoolean("option_chain_available", false) ? "CHAIN READY" : "CHAIN UNAVAILABLE";
                card(
                    "#" + x.optInt("rank") + "  " + x.optString("symbol") + "\n\n" +
                    "Spot: ₹" + x.optString("price", "n/a") +
                    " | Change: " + x.optString("change_pct", "n/a") + "%\n" +
                    "Setup score: " + x.optString("setup_quality_score", "n/a") + "/100\n" +
                    "Status: " + chain + "\n\n" +
                    x.optString("option_summary", "Detailed option-chain data unavailable.")
                );
            }
            JSONArray analyses = latest.optJSONArray("ai_analyses");
            if (analyses != null && analyses.length() > 0) {
                heading("🤖 AI ANALYSIS");
                for (int i = 0; i < analyses.length(); i++) {
                    JSONObject a = analyses.optJSONObject(i);
                    if (a != null) card(a.optString("provider", "AI") + "\n\n" + a.optString("analysis", ""));
                }
            }
        } else {
            heading("🔥 TECHNICAL BREAKOUT WATCH");
            JSONArray breakouts = latest.optJSONArray("breakouts");
            if (breakouts == null || breakouts.length() == 0) {
                card("Breakout scanner is prepared in the app UI. Technical pattern detection will populate this section in the next engine phase.\n\nThe app will show: pattern, resistance/support, distance to trigger, volume confirmation, EMA structure and WAIT/READY status.");
            }
        }
    }

    private void showMessage(String text) {
        clear();
        card(text);
    }
}
