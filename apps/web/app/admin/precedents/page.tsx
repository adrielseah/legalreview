"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Upload,
  Search,
  Trash2,
  Eye,
  EyeOff,
  ChevronLeft,
  ChevronRight,
  Database,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  FileUp,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  deletePrecedent,
  getPrecedentStats,
  getJob,
  importCsvPrecedents,
  listPrecedents,
  previewCsvImport,
  updatePrecedent,
} from "@/lib/api";
import { formatDate, truncate } from "@/lib/utils";
import type { PrecedentClause } from "@clauselens/shared";

const PAGE_SIZE = 50;

export default function AdminPrecedentsPage() {
  const [items, setItems] = useState<PrecedentClause[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState({ total: 0, active: 0, rejected: 0 });
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeOnly, setActiveOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editNotes, setEditNotes] = useState("");
  const [editSource, setEditSource] = useState("");
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [importOpen, setImportOpen] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [list, s] = await Promise.all([
        listPrecedents({
          query: searchQuery || undefined,
          active_only: activeOnly,
          limit: PAGE_SIZE,
          offset: (page - 1) * PAGE_SIZE,
        }),
        getPrecedentStats(),
      ]);
      setItems(list.items);
      setTotal(list.total);
      setStats(s);
    } catch (e: any) {
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [searchQuery, activeOnly, page]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggleActive = async (id: string, current: boolean) => {
    await updatePrecedent(id, { is_active: !current });
    loadData();
  };

  const handleSaveEdit = async (id: string) => {
    await updatePrecedent(id, {
      notes: editNotes || null,
      source_document: editSource || null,
    });
    setEditingId(null);
    loadData();
  };

  const handleDelete = async (id: string) => {
    await deletePrecedent(id);
    setDeleteConfirmId(null);
    loadData();
  };

  const totalPages = Math.ceil(total / PAGE_SIZE);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Precedents</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage accepted and rejected clause precedents
          </p>
        </div>
        <Button onClick={() => setImportOpen(true)} className="gap-2">
          <FileUp className="h-4 w-4" />
          Import CSV
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 max-w-sm">
        <StatCard label="Total" value={stats.total} icon={<Database className="h-4 w-4 text-blue-400" />} />
        <StatCard label="Active" value={stats.active} icon={<CheckCircle2 className="h-4 w-4 text-emerald-400" />} />
        <StatCard label="Rejected" value={stats.rejected} icon={<AlertTriangle className="h-4 w-4 text-red-400" />} />
      </div>

      <Separator />

      {/* Filters */}
      <div className="flex items-center gap-3">
        <div className="relative max-w-sm flex-1">
          <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="Search clause text, source, notes…"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setPage(1);
            }}
            className="pl-8"
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="active_only"
            checked={activeOnly}
            onCheckedChange={(v) => {
              setActiveOnly(v);
              setPage(1);
            }}
          />
          <Label htmlFor="active_only" className="text-sm">
            Active only
          </Label>
        </div>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex items-center gap-2 text-muted-foreground text-sm py-8">
          <Loader2 className="h-4 w-4 animate-spin" />
          Loading…
        </div>
      ) : items.length === 0 ? (
        <div className="text-center py-16 text-muted-foreground">
          <Database className="h-8 w-8 mx-auto mb-3 opacity-30" />
          <p className="text-sm">No precedents found.</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border overflow-hidden">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border bg-muted/30">
                <th className="text-left px-3 py-2 font-medium text-muted-foreground w-2/5">
                  Clause Text
                </th>
                <th className="text-left px-3 py-2 font-medium text-muted-foreground">
                  Source
                </th>
                <th className="text-left px-3 py-2 font-medium text-muted-foreground w-32">
                  Notes
                </th>
                <th className="text-left px-3 py-2 font-medium text-muted-foreground">
                  Status
                </th>
                <th className="text-left px-3 py-2 font-medium text-muted-foreground">
                  Added
                </th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => (
                <>
                  <tr
                    key={item.id}
                    className="border-b border-border hover:bg-accent/20 transition-colors"
                  >
                    <td className="px-3 py-2.5">
                      <div>
                        <p className="line-clamp-2 leading-relaxed">
                          {expandedId === item.id
                            ? item.clause_text
                            : truncate(item.clause_text, 120)}
                        </p>
                        <button
                          onClick={() =>
                            setExpandedId(expandedId === item.id ? null : item.id)
                          }
                          className="text-[10px] text-blue-400 hover:underline mt-0.5"
                        >
                          {expandedId === item.id ? "Show less" : "Expand"}
                        </button>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground">
                      {editingId === item.id ? (
                        <Input
                          value={editSource}
                          onChange={(e) => setEditSource(e.target.value)}
                          className="h-7 text-xs"
                          placeholder="Source document"
                        />
                      ) : (
                        item.source_document || "—"
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      {editingId === item.id ? (
                        <Textarea
                          value={editNotes}
                          onChange={(e) => setEditNotes(e.target.value)}
                          className="min-h-[56px] text-xs"
                          placeholder="Notes"
                        />
                      ) : (
                        <span className="text-muted-foreground line-clamp-2">
                          {item.notes || "—"}
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="space-y-1">
                        <Badge
                          variant={
                            item.sentiment === "rejected" ? "danger" : "success"
                          }
                        >
                          {item.sentiment === "rejected" ? "Rejected" : "Accepted"}
                        </Badge>
                        <div className="flex items-center gap-1">
                          <Switch
                            checked={item.is_active}
                            onCheckedChange={() =>
                              handleToggleActive(item.id, item.is_active)
                            }
                            className="scale-75"
                          />
                          <span className="text-[10px] text-muted-foreground">
                            {item.is_active ? "Active" : "Disabled"}
                          </span>
                        </div>
                      </div>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground text-[10px]">
                      {formatDate(item.created_at)}
                    </td>
                    <td className="px-3 py-2.5">
                      <div className="flex items-center gap-1">
                        {editingId === item.id ? (
                          <>
                            <Button
                              size="sm"
                              className="h-6 text-[10px] px-2"
                              onClick={() => handleSaveEdit(item.id)}
                            >
                              Save
                            </Button>
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-6 w-6"
                              onClick={() => setEditingId(null)}
                            >
                              <X className="h-3 w-3" />
                            </Button>
                          </>
                        ) : (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-6 text-[10px] px-2"
                            onClick={() => {
                              setEditingId(item.id);
                              setEditNotes(item.notes || "");
                              setEditSource(item.source_document || "");
                            }}
                          >
                            Edit
                          </Button>
                        )}
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6 text-destructive hover:text-destructive"
                          onClick={() => setDeleteConfirmId(item.id)}
                        >
                          <Trash2 className="h-3 w-3" />
                        </Button>
                      </div>
                    </td>
                  </tr>
                </>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center gap-2 justify-end">
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            disabled={page === 1}
            onClick={() => setPage((p) => p - 1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="text-sm text-muted-foreground">
            {page} / {totalPages} ({total} total)
          </span>
          <Button
            variant="outline"
            size="icon"
            className="h-8 w-8"
            disabled={page === totalPages}
            onClick={() => setPage((p) => p + 1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      )}

      {/* Delete confirm dialog */}
      <Dialog
        open={!!deleteConfirmId}
        onOpenChange={(open) => !open && setDeleteConfirmId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete Precedent</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            Are you sure you want to permanently delete this precedent? This cannot
            be undone. Consider disabling it instead.
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteConfirmId(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteConfirmId && handleDelete(deleteConfirmId)}
            >
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* CSV Import dialog */}
      <CsvImportDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        onImported={loadData}
      />
    </div>
  );
}

function StatCard({
  label,
  value,
  icon,
}: {
  label: string;
  value: number;
  icon: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card px-3 py-2.5 flex items-center gap-2">
      {icon}
      <div>
        <p className="text-lg font-bold leading-none">{value}</p>
        <p className="text-[10px] text-muted-foreground mt-0.5">{label}</p>
      </div>
    </div>
  );
}

function CsvImportDialog({
  open,
  onOpenChange,
  onImported,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onImported: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<any | null>(null);
  const [importing, setImporting] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<string | null>(null);
  const [jobDetail, setJobDetail] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (f: File) => {
    setFile(f);
    setPreview(null);
    setError(null);
    try {
      const p = await previewCsvImport(f);
      setPreview(p);
    } catch (e: any) {
      setError(e.message);
    }
  };

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    setError(null);
    try {
      const result = await importCsvPrecedents(file);
      setJobId(result.job_id);
      // Poll job
      const interval = setInterval(async () => {
        try {
          const job = await getJob(result.job_id);
          setJobStatus(job.status);
          setJobDetail(job.progress_detail);
          if (job.status === "done" || job.status === "failed") {
            clearInterval(interval);
            setImporting(false);
            if (job.status === "done") {
              onImported();
              setTimeout(() => {
                onOpenChange(false);
                setFile(null);
                setPreview(null);
                setJobId(null);
                setJobStatus(null);
                setJobDetail(null);
              }, 1500);
            }
          }
        } catch {}
      }, 1500);
    } catch (e: any) {
      setError(e.message);
      setImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Upload className="h-5 w-5" />
            Import Precedents from CSV
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-xs text-muted-foreground">
            Required column: <code className="bg-muted px-1 rounded">clause_text</code>.
            Optional:{" "}
            <code className="bg-muted px-1 rounded">source_document</code>,{" "}
            <code className="bg-muted px-1 rounded">notes</code>,{" "}
            <code className="bg-muted px-1 rounded">sentiment</code>{" "}
            (accepted|rejected).
          </p>

          <div
            className="border-2 border-dashed rounded-lg p-6 text-center cursor-pointer hover:border-muted-foreground/50 transition-colors"
            onClick={() => fileRef.current?.click()}
          >
            <input
              ref={fileRef}
              type="file"
              accept=".csv"
              className="hidden"
              onChange={(e) => e.target.files?.[0] && handleFileChange(e.target.files[0])}
            />
            <FileUp className="h-6 w-6 mx-auto mb-2 text-muted-foreground" />
            {file ? (
              <p className="text-sm font-medium">{file.name}</p>
            ) : (
              <p className="text-sm text-muted-foreground">Click to select a .csv file</p>
            )}
          </div>

          {preview && (
            <div className="rounded-md bg-muted/30 border border-border p-3 space-y-2">
              <div className="flex gap-4 text-xs">
                <span className="text-emerald-400 font-medium">
                  {preview.valid_rows} valid rows
                </span>
                {preview.invalid_rows > 0 && (
                  <span className="text-red-400">
                    {preview.invalid_rows} invalid
                  </span>
                )}
              </div>
              {preview.sample_rows.length > 0 && (
                <div className="space-y-1">
                  <p className="text-[10px] text-muted-foreground font-medium">
                    Sample rows:
                  </p>
                  {preview.sample_rows.map((row: any, i: number) => (
                    <p key={i} className="text-[10px] text-muted-foreground line-clamp-1">
                      • {truncate(row.clause_text, 80)}
                    </p>
                  ))}
                </div>
              )}
            </div>
          )}

          {jobId && (
            <div className="rounded-md bg-blue-950/30 border border-blue-700/30 p-3 space-y-1.5">
              <div className="flex items-center gap-2 text-xs">
                {importing ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-blue-400" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
                )}
                <span>
                  {jobStatus === "done" ? "Import complete!" : "Importing…"}
                </span>
              </div>
              {jobDetail && (
                <p className="text-[10px] text-muted-foreground">{jobDetail}</p>
              )}
            </div>
          )}

          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Close
          </Button>
          <Button
            onClick={handleImport}
            disabled={!file || !preview || importing || preview.valid_rows === 0}
            className="gap-1.5"
          >
            {importing && <Loader2 className="h-4 w-4 animate-spin" />}
            Import {preview?.valid_rows || 0} rows
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
