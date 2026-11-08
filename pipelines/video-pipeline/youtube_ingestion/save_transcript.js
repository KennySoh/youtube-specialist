/* "Save transcript" bookmarklet (./scripts/yt.sh bookmarklet prints it). On a YouTube watch page with the
   transcript panel open, it saves what the panel shows as <video_id>.transcript.json for ./scripts/yt.sh import.
   It only reads the page that is already on screen: no requests. */
(function () {
  var id = new URLSearchParams(location.search).get("v") ||
    ((location.pathname.match(/\/(?:shorts|live)\/([A-Za-z0-9_-]{11})/) || [])[1]);
  if (!id) { alert("Not a YouTube video page."); return; }

  var panels = Array.prototype.slice.call(document.querySelectorAll(
    "ytd-engagement-panel-section-list-renderer[visibility='ENGAGEMENT_PANEL_VISIBILITY_EXPANDED']"));
  var root = panels.length ? panels : [document];

  var segments = [];
  root.forEach(function (el) {
    el.querySelectorAll("ytd-transcript-segment-renderer, transcript-segment-view-model").forEach(function (seg) {
      var t = seg.querySelector(".segment-timestamp, [class*='timestamp']");
      var x = seg.querySelector(".segment-text, yt-formatted-string:not([class*='timestamp']), [role='text']");
      if (t && x && x.textContent.trim()) {
        segments.push({ t: t.textContent.trim(), text: x.textContent.trim() });
      }
    });
  });
  var panelText = panels.map(function (p) { return p.innerText; }).join("\n");

  var title = (document.querySelector("ytd-watch-metadata h1") || {}).textContent ||
    document.title.replace(/ - YouTube$/, "");
  var channel = (document.querySelector("ytd-watch-metadata ytd-channel-name a") || {}).textContent || "";
  var data = {
    video_id: id, title: title.trim(), channel: channel.trim(),
    url: "https://www.youtube.com/watch?v=" + id, captured_at: new Date().toISOString(),
    segments: segments, panel_text: panelText
  };

  if (!segments.length && !panelText.trim()) { alert("Nothing to save: open the transcript panel first."); return; }

  var a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 1)], { type: "application/json" }));
  a.download = id + ".transcript.json";
  document.body.appendChild(a); a.click(); a.remove();
  alert(segments.length ? "Saved " + segments.length + " segments for " + id
    : "Saved the panel text for " + id + " (./scripts/yt.sh import will parse it)");
})();
