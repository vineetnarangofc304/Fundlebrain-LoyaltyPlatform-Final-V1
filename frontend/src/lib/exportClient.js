/* Shared report-export client. Every export button funnels through requestExport():
   small results (server decides via known_total) download instantly; large ones are
   generated in the background and surfaced in the Downloads Center. */
import api from "./api";
import { toast } from "sonner";

export async function downloadExport(exportId, filename) {
  const res = await api.get(`/exports/${exportId}/download`, { responseType: "blob" });
  const url = window.URL.createObjectURL(new Blob([res.data], { type: "text/csv" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `${exportId}.csv`;
  a.click();
  window.URL.revokeObjectURL(url);
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
