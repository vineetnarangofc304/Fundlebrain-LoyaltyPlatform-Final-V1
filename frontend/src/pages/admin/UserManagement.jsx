import { useEffect, useState } from "react";
import api from "@/lib/api";
import { PageHeader, StatusPill } from "./_shared";
import { toast } from "sonner";
import { fmtDate } from "@/lib/format";
import { Plus, UserPlus, KeyRound, Power, ShieldAlert, Eye } from "lucide-react";
import { useAuth } from "@/lib/auth";

const ROLES = [
  "super_admin","brand_admin","crm_manager","marketing_manager","regional_manager",
  "store_manager","store_staff","support_agent","analytics_viewer","readonly_executive",
];

export default function UserManagement() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState([]);
  const [show, setShow] = useState(false);
  const [form, setForm] = useState({ email: "", name: "", password: "", role: "store_manager", phone: "", region: "", is_master_admin: false });
  const [pwModal, setPwModal] = useState(null);
  const [newPw, setNewPw] = useState("");

  const load = async () => {
    const r = await api.get("/users");
    setUsers(r.data);
  };
  useEffect(() => { load(); }, []);

  const create = async () => {
    try {
      await api.post("/users", form);
      toast.success(`User ${form.email} created`);
      setShow(false);
      setForm({ email: "", name: "", password: "", role: "store_manager", phone: "", region: "", is_master_admin: false });
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const toggleActive = async (u) => {
    try {
      await api.patch(`/users/${u.id}`, { is_active: !u.is_active });
      toast.success(`User ${u.is_active ? "deactivated" : "activated"}`);
      load();
    } catch (e) {
      toast.error("Failed");
    }
  };

  const toggleMaster = async (u) => {
    try {
      await api.patch(`/users/${u.id}`, { is_master_admin: !u.is_master_admin });
      toast.success(`Master Admin ${u.is_master_admin ? "revoked" : "granted"} for ${u.email}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const toggleQueryAdmin = async (u) => {
    try {
      await api.patch(`/users/${u.id}`, { is_master_query_admin: !u.is_master_query_admin });
      toast.success(`Master Query Admin ${u.is_master_query_admin ? "revoked" : "granted"} for ${u.email}`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Failed");
    }
  };

  const resetPw = async () => {
    try {
      await api.post(`/users/${pwModal}/reset-password`, null, { params: { new_password: newPw } });
      toast.success("Password reset");
      setPwModal(null); setNewPw("");
    } catch (e) { toast.error("Failed"); }
  };

  const availableRoles = me?.role === "super_admin" ? ROLES : ROLES.filter((r) => r !== "super_admin");

  return (
    <div data-testid="user-management-page">
      <PageHeader title="User Management" subtitle="ROLE-BASED ACCESS"
        actions={<button className="k-btn kazo-bg-burgundy" onClick={() => setShow(true)} data-testid="new-user-btn"><UserPlus className="w-4 h-4" /> New user</button>} />
      <div className="p-8">
        <div className="bg-white border border-black/10 overflow-x-auto">
          <table className="data-table">
            <thead><tr><th>Name</th><th>Email</th><th>Role</th><th>Phone</th><th>Last login</th><th>Created</th><th>Status</th><th>Master</th><th></th></tr></thead>
            <tbody>
              {users.map((u) => (
                <tr key={u.id} data-testid={`user-row-${u.id}`}>
                  <td className="font-medium">{u.name}</td>
                  <td className="font-mono text-xs">{u.email}</td>
                  <td><span className="pill pill-neutral">{u.role.replace(/_/g, " ")}</span></td>
                  <td className="text-xs">{u.phone || "—"}</td>
                  <td className="text-xs">{u.last_login_at ? fmtDate(u.last_login_at) : "—"}</td>
                  <td className="text-xs">{fmtDate(u.created_at)}</td>
                  <td><StatusPill status={u.is_active ? "active" : "inactive"} /></td>
                  <td>
                    {u.is_master_admin
                      ? <span className="pill" style={{ background: "#FEE2E2", color: "#991B1B" }} data-testid={`master-badge-${u.id}`}>Master</span>
                      : <span className="text-xs text-neutral-400">—</span>}
                    {u.is_master_query_admin && <span className="pill ml-1" style={{ background: "#E0E7FF", color: "#3730A3" }} data-testid={`query-badge-${u.id}`}>Query</span>}
                  </td>
                  <td>
                    <div className="flex gap-1">
                      {me?.role === "super_admin" && (
                        <button className="k-btn k-btn-ghost k-btn-sm" title={u.is_master_admin ? "Revoke Master Admin" : "Grant Master Admin"} onClick={() => toggleMaster(u)} data-testid={`master-toggle-${u.id}`}>
                          <ShieldAlert className={`w-3.5 h-3.5 ${u.is_master_admin ? "text-red-600" : ""}`} />
                        </button>
                      )}
                      {me?.role === "super_admin" && (
                        <button className="k-btn k-btn-ghost k-btn-sm" title={u.is_master_query_admin ? "Revoke Master Query Admin (sees ALL Master Brain queries)" : "Grant Master Query Admin (sees ALL Master Brain queries)"} onClick={() => toggleQueryAdmin(u)} data-testid={`query-toggle-${u.id}`}>
                          <Eye className={`w-3.5 h-3.5 ${u.is_master_query_admin ? "text-indigo-600" : ""}`} />
                        </button>
                      )}
                      <button className="k-btn k-btn-ghost k-btn-sm" title="Reset password" onClick={() => setPwModal(u.id)} data-testid={`reset-${u.id}`}><KeyRound className="w-3.5 h-3.5" /></button>
                      <button className="k-btn k-btn-ghost k-btn-sm" title={u.is_active ? "Deactivate" : "Activate"} onClick={() => toggleActive(u)} data-testid={`toggle-${u.id}`}><Power className="w-3.5 h-3.5" /></button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {show && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShow(false)}>
          <div className="bg-white p-6 w-full max-w-lg" onClick={(e) => e.stopPropagation()} data-testid="new-user-modal">
            <h3 className="font-display text-2xl mb-4">Add User</h3>
            <div className="space-y-3">
              <input className="k-input" placeholder="Full name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="new-user-name" />
              <input className="k-input" placeholder="Email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} data-testid="new-user-email" />
              <input className="k-input" placeholder="Password" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} data-testid="new-user-password" />
              <input className="k-input" placeholder="Phone (optional)" value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} />
              <select className="k-input" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })} data-testid="new-user-role">
                {availableRoles.map((r) => <option key={r} value={r}>{r.replace(/_/g, " ")}</option>)}
              </select>
              <input className="k-input" placeholder="Region (optional)" value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} />
              {me?.role === "super_admin" && (
                <label className="flex items-center gap-2 text-sm cursor-pointer select-none" data-testid="new-user-master">
                  <input type="checkbox" checked={!!form.is_master_admin} onChange={(e) => setForm({ ...form, is_master_admin: e.target.checked })} />
                  <ShieldAlert className={`w-4 h-4 ${form.is_master_admin ? "text-red-600" : "text-neutral-400"}`} />
                  Grant <b>Master Admin</b> (can take live actions via Master Brain)
                </label>
              )}
              {me?.role === "super_admin" && (
                <label className="flex items-center gap-2 text-sm cursor-pointer select-none" data-testid="new-user-query-admin">
                  <input type="checkbox" checked={!!form.is_master_query_admin} onChange={(e) => setForm({ ...form, is_master_query_admin: e.target.checked })} />
                  <Eye className={`w-4 h-4 ${form.is_master_query_admin ? "text-indigo-600" : "text-neutral-400"}`} />
                  Grant <b>Master Query Admin</b> (can see the Master Brain query log of ALL users)
                </label>
              )}
              <div className="flex justify-end gap-2 mt-2">
                <button className="k-btn k-btn-ghost" onClick={() => setShow(false)}>Cancel</button>
                <button className="k-btn kazo-bg-burgundy" onClick={create} data-testid="new-user-submit">Create user</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {pwModal && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setPwModal(null)}>
          <div className="bg-white p-6 w-full max-w-md" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-2xl mb-4">Reset Password</h3>
            <input className="k-input" type="password" placeholder="New password (min 6 chars)" value={newPw} onChange={(e) => setNewPw(e.target.value)} data-testid="reset-pw-input" />
            <div className="flex justify-end gap-2 mt-4">
              <button className="k-btn k-btn-ghost" onClick={() => setPwModal(null)}>Cancel</button>
              <button className="k-btn kazo-bg-burgundy" onClick={resetPw} data-testid="reset-pw-confirm">Reset</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
