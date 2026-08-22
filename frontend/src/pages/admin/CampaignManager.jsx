import { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { PageHeader, StatusPill } from "./_shared";
import { toast } from "sonner";
import { fmtMoney2, fmtNum, fmtDate } from "@/lib/format";
import { Plus, Play, Send, MessageSquare, Mail, Smartphone, Loader2, TrendingUp, Truck, ShieldBan, Bot, Trash2 } from "lucide-react";
import CampaignRoiModal from "./campaigns/CampaignRoiModal";
import CampaignWizard from "./campaigns/CampaignWizard";
import CampaignDeliveryModal from "./campaigns/CampaignDeliveryModal";
import CampaignBlacklistModal from "./campaigns/CampaignBlacklistModal";

const CHANNEL_ICON = { whatsapp: MessageSquare, sms: Smartphone, rcs: MessageSquare, email: Mail };

export default function CampaignManager() {
  const [items, setItems] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [coupons, setCoupons] = useState([]);
  const [showWizard, setShowWizard] = useState(false);
  const [wizardPrefill, setWizardPrefill] = useState(null);
  const [showBlacklist, setShowBlacklist] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const [launching, setLaunching] = useState(null);
  const [roiCampaign, setRoiCampaign] = useState(null);
  const [deliveryCampaign, setDeliveryCampaign] = useState(null);
  const pollRef = useRef(null);

  const load = async () => {
    const [c, co, tpl] = await Promise.all([
      api.get("/campaigns"),
      api.get("/coupons", { params: { is_active: true } }),
      api.get("/templates", { params: { status: "active" } }).catch(() => ({ data: [] })),
    ]);
    setItems(c.data);
    setCoupons(co.data);
    setTemplates(Array.isArray(tpl.data) ? tpl.data : []);
  };
  useEffect(() => { load(); }, []);

  // Prefill from Segment Builder / Marketing Database → open the wizard pre-seeded
  useEffect(() => {
    const segmentId = searchParams.get("segment_id");
    const segmentName = searchParams.get("segment_name");
    const mdbId = searchParams.get("marketing_db_id");
    const mdbName = searchParams.get("marketing_db_name");
    if (segmentId) {
      setWizardPrefill({
        name: segmentName ? `Campaign · ${segmentName}` : "",
        audience_type: "segment",
        audience_filter: { segment_id: segmentId, segment_name: segmentName },
      });
      setShowWizard(true);
      setSearchParams({}, { replace: true });
      toast.info(`Campaign prefilled with segment "${segmentName || segmentId}"`);
    } else if (mdbId) {
      setWizardPrefill({
        name: mdbName ? `Campaign · ${mdbName}` : "",
        audience_type: "marketing_db",
        audience_filter: { marketing_db_id: mdbId, marketing_db_name: mdbName },
      });
      setShowWizard(true);
      setSearchParams({}, { replace: true });
      toast.info(`Campaign prefilled with marketing database "${mdbName || mdbId}"`);
    }
  }, [searchParams, setSearchParams]);

  // Poll running campaigns with a bulk_job_id for live progress
  useEffect(() => {
    const runningWithJob = items.filter((c) => c.status === "running" && c.bulk_job_id);
    if (runningWithJob.length === 0) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    const tick = async () => {
      try {
        const updates = await Promise.all(
          runningWithJob.map((c) =>
            api.get(`/communications/bulk-jobs/${c.bulk_job_id}`).then((r) => ({ id: c.id, job: r.data })).catch(() => null)
          )
        );
        setItems((prev) => prev.map((c) => {
          const u = updates.find((x) => x && x.id === c.id);
          if (!u || !u.job) return c;
          const j = u.job;
          return { ...c, _job: j, sent: j.sent || c.sent, status: j.status === "completed" ? "completed" : (j.status === "failed" ? "cancelled" : c.status) };
        }));
      } catch { /* ignore */ }
    };
    tick();
    pollRef.current = setInterval(tick, 4000);
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [items.map((c) => c.id + ":" + c.status).join("|")]);

  const launch = async (id) => {
    setLaunching(id);
    try {
      const r = await api.post(`/campaigns/${id}/launch`);
      if (r.data.mode === "karix") toast.success(`Real send via ${r.data.channel.toUpperCase()} queued · audience ${fmtNum(r.data.audience)}`);
      else toast.success(`Simulated metrics generated · audience ${fmtNum(r.data.audience)} (link a template for real send)`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Launch failed");
    } finally { setLaunching(null); }
  };

  const openWizard = () => { setWizardPrefill(null); setShowWizard(true); };

  const del = async (c) => {
    if (!window.confirm(`Delete campaign "${c.name}"? This also removes its frozen ROI dataset.`)) return;
    try {
      await api.delete(`/campaigns/${c.id}`);
      toast.success("Campaign deleted");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Delete failed");
    }
  };

  const unschedule = async (c) => {
    try {
      await api.post(`/campaigns/${c.id}/unschedule`);
      toast.success("Schedule cancelled — moved back to draft");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed to unschedule");
    }
  };

  return (
    <div data-testid="campaign-manager">
      <PageHeader title="Campaign Manager" subtitle="GUIDED WORKFLOW · REAL ROI · KARIX DELIVERY"
        actions={
          <div className="flex gap-2">
            <button className="k-btn k-btn-ghost" onClick={() => setShowBlacklist(true)} data-testid="open-blacklist-btn"><ShieldBan className="w-4 h-4" /> Blacklist</button>
            <button className="k-btn kazo-bg-burgundy" onClick={openWizard} data-testid="new-campaign-btn"><Plus className="w-4 h-4" /> New campaign</button>
          </div>
        } />
      <div className="p-8">
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Campaign</th><th>Channels</th><th>Audience</th><th>Send Mode</th><th className="text-right">Sent</th><th className="text-right">Delivered</th><th className="text-right">Redeemed</th><th className="text-right">Revenue</th><th>Status</th><th></th></tr></thead>
            <tbody>
              {items.map((c) => {
                const job = c._job;
                const ChannelIcon = CHANNEL_ICON[c.channels?.[0]] || MessageSquare;
                const canReport = c.launched_at || c.status === "running" || c.status === "completed";
                const sim = c.send_mode === "simulated";
                const simCls = sim ? "text-neutral-300" : "";
                const simTitle = sim ? "Simulated demo metric — see the ROI modal for real attribution" : undefined;
                return (
                  <tr key={c.id} data-testid={`campaign-row-${c.id}`}>
                    <td>
                      <div className="font-medium flex items-center gap-1.5">
                        {c.source === "master_brain" && <span className="pill pill-info flex items-center gap-1" data-testid={`mb-pill-${c.id}`}><Bot className="w-3 h-3" /> MB</span>}
                        {c.name}
                      </div>
                      <div className="text-xs text-neutral-500">{fmtDate(c.created_at)}{c.bulk_job_id ? ` · job ${c.bulk_job_id.slice(0, 8)}` : ""}</div>
                      {c.status === "scheduled" && c.schedule_at && (
                        <div className="text-[11px] text-indigo-600 mt-0.5" data-testid={`sched-time-${c.id}`}>⏱ Fires {new Date(c.schedule_at).toLocaleString()}</div>
                      )}
                    </td>
                    <td><div className="flex gap-1 flex-wrap">{c.channels?.map((ch) => <span key={ch} className="pill pill-neutral">{ch}</span>)}</div></td>
                    <td><span className="pill pill-info">{c.audience_type}</span></td>
                    <td>
                      {c.send_mode === "karix" ? (
                        <span className="pill" style={{ background: "#dcfce7", color: "#166534" }} data-testid={`send-mode-${c.id}`}><ChannelIcon className="w-3 h-3 inline mr-1" /> Real Karix</span>
                      ) : c.send_mode === "simulated" ? (
                        <span className="pill pill-neutral" data-testid={`send-mode-${c.id}`}>Simulated</span>
                      ) : c.template_id ? (
                        <span className="pill pill-info">Karix · ready</span>
                      ) : (
                        <span className="pill pill-warning">No template</span>
                      )}
                    </td>
                    <td className="text-right font-mono">
                      {fmtNum(c.sent)}
                      {job && job.status === "running" && <div className="text-[10px] text-neutral-400">{job.processed || 0}/{job.audience_size_total || "?"}</div>}
                    </td>
                    <td className={`text-right font-mono ${simCls}`} title={simTitle}>{fmtNum(c.delivered)}</td>
                    <td className={`text-right font-mono ${simCls}`} title={simTitle}>{fmtNum(c.redeemed)}</td>
                    <td className={`text-right font-mono ${simCls}`} title={simTitle}>{fmtMoney2(c.revenue_generated)}</td>
                    <td>
                      <StatusPill status={c.status} />
                      {job && job.failed > 0 && <div className="text-[10px] text-rose-600 mt-0.5">{job.failed} failed</div>}
                    </td>
                    <td>
                      <div className="flex gap-1 justify-end">
                        {c.status === "draft" && (
                          <button className="k-btn k-btn-sm kazo-bg-burgundy disabled:opacity-50" onClick={() => launch(c.id)} disabled={launching === c.id} data-testid={`launch-${c.id}`}>
                            {launching === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                            {launching === c.id ? "Launching…" : "Launch"}
                          </button>
                        )}
                        {c.status === "scheduled" && (
                          <>
                            <button className="k-btn k-btn-sm kazo-bg-burgundy disabled:opacity-50" onClick={() => launch(c.id)} disabled={launching === c.id} data-testid={`launch-now-${c.id}`}>
                              {launching === c.id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />} Launch now
                            </button>
                            <button className="k-btn k-btn-sm k-btn-ghost" onClick={() => unschedule(c)} data-testid={`unschedule-${c.id}`}>Unschedule</button>
                          </>
                        )}
                        {canReport && (
                          <>
                            <button className="k-btn k-btn-sm k-btn-ghost" onClick={() => setRoiCampaign(c)} data-testid={`roi-${c.id}`}><TrendingUp className="w-3 h-3" /> ROI</button>
                            <button className="k-btn k-btn-sm k-btn-ghost" onClick={() => setDeliveryCampaign(c)} data-testid={`delivery-${c.id}`}><Truck className="w-3 h-3" /> Delivery</button>
                          </>
                        )}
                        {c.status !== "running" && (
                          <button className="k-btn k-btn-sm k-btn-ghost text-rose-600" onClick={() => del(c)} data-testid={`delete-${c.id}`} title="Delete campaign"><Trash2 className="w-3 h-3" /></button>
                        )}
                      </div>
                    </td>
                  </tr>
                );
              })}
              {items.length === 0 && <tr><td colSpan={10} className="text-center py-10 text-neutral-500">No campaigns yet — click “New campaign” to start the guided wizard</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {showWizard && (
        <CampaignWizard
          templates={templates} coupons={coupons} prefill={wizardPrefill}
          onClose={() => setShowWizard(false)}
          onDone={() => { setShowWizard(false); load(); }}
        />
      )}
      {roiCampaign && <CampaignRoiModal campaign={roiCampaign} onClose={() => setRoiCampaign(null)} />}
      {deliveryCampaign && <CampaignDeliveryModal campaign={deliveryCampaign} onClose={() => setDeliveryCampaign(null)} />}
      {showBlacklist && <CampaignBlacklistModal onClose={() => setShowBlacklist(false)} />}
    </div>
  );
}
