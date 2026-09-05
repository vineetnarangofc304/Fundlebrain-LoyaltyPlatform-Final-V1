/* Shared report-export client. Every export button funnels through requestExport():
   small results (server decides via known_total) download instantly; large ones are
   generated in the background and surfaced in the Downloads Center. */
import api, { API_URL } from "./api";
import { toast } from "sonner";

export function downloadExport(exportId, filename) {
  // Native, streamed browser download — the JWT rides on the httpOnly kazo_token
  // cookie (same origin), so we never buffer a huge file through axios/JS memory.
  const a = document.createElement("a");
  a.href = `${API_URL}/exports/${exportId}/download`;
  a.download = filename || `${exportId}.csv`;
  document.body.appendChild(a);
  a.click();
  a.remove();
}

export async function requestExport({ report_type, params = {}, label, known_total = null, filename }) {
  try {
    const r = await api.post("/exports/request", { report_type, params, label, known_total });
    if (r.data.status === "ready" && r.data.export_id) {
      await downloadExport(r.data.export_id, filename);
      toast.success("Download started");
    } else {
      toast.success("Download started", {
        description: "Your report is being prepared — find it in the Downloads section.",
        duration: 6000,
      });
      window.dispatchEvent(new CustomEvent("kazo-export-requested"));
    }
    return r.data;
  } catch (e) {
    toast.error(e.response?.data?.detail || "Export failed");
    throw e;
  }
}
