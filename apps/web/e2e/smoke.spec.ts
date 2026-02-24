/**
 * ClauseLens smoke test suite.
 *
 * Prerequisites:
 *  - All docker-compose services running: docker compose up -d
 *  - DISABLE_LLM=true, DISABLE_EMBEDDINGS=true (set in docker-compose env or .env)
 *  - sample.docx fixture exists at apps/api/tests/fixtures/sample.docx
 *
 * Tests:
 *  1. Vendors page loads and shows empty state or list
 *  2. Create a new vendor case
 *  3. Upload a fixture DOCX file
 *  4. Poll until processing completes
 *  5. Review page loads and shows clause list
 *  6. Admin precedents page loads
 *  7. CSV import preview and import flow
 */

import { test, expect, Page } from "@playwright/test";
import path from "path";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const FIXTURE_DOCX = path.join(__dirname, "../../api/tests/fixtures/sample.docx");
const FIXTURE_CSV = path.join(__dirname, "fixtures/sample_precedents.csv");

// Helper: wait for job completion by polling the API
async function waitForJobDone(page: Page, jobId: string, maxMs = 90_000): Promise<void> {
  const start = Date.now();
  while (Date.now() - start < maxMs) {
    const res = await page.request.get(`${API_BASE}/jobs/${jobId}`);
    if (res.ok()) {
      const body = await res.json();
      if (body.status === "done") return;
      if (body.status === "failed") throw new Error(`Job ${jobId} failed: ${body.error}`);
    }
    await page.waitForTimeout(2000);
  }
  throw new Error(`Job ${jobId} did not complete within ${maxMs}ms`);
}

test.describe("ClauseLens Smoke Tests", () => {
  let vendorCaseId: string;
  let documentId: string;
  let jobId: string;

  test("1. Vendors page loads", async ({ page }) => {
    await page.goto("/vendors");
    await expect(page).toHaveTitle(/ClauseLens/);
    await expect(page.getByRole("heading", { name: "Vendor Cases" })).toBeVisible();
    await expect(page.getByRole("button", { name: "New Vendor Case" })).toBeVisible();
  });

  test("2. Create a new vendor case", async ({ page }) => {
    await page.goto("/vendors");
    await page.getByRole("button", { name: "New Vendor Case" }).click();

    // Fill in form
    await page.getByLabel("Vendor Name").fill("Smoke Test Vendor Co.");
    await page.getByLabel(/Procurement Reference/i).fill("PR-SMOKE-001");
    await page.getByRole("button", { name: "Create" }).click();

    // Should redirect or refresh and show the vendor
    await page.waitForTimeout(1000);

    // Verify via API
    const res = await page.request.get(`${API_BASE}/vendors?q=Smoke+Test+Vendor`);
    expect(res.ok()).toBeTruthy();
    const vendors = await res.json();
    expect(vendors.length).toBeGreaterThan(0);
    vendorCaseId = vendors[0].id;

    // Store for subsequent tests
    process.env._TEST_VENDOR_ID = vendorCaseId;
  });

  test("3. Vendor dashboard loads and upload form is visible", async ({ page }) => {
    vendorCaseId = process.env._TEST_VENDOR_ID || vendorCaseId;
    if (!vendorCaseId) {
      test.skip(!vendorCaseId, "Vendor not created");
      return;
    }

    await page.goto(`/vendors/${vendorCaseId}`);
    await expect(page.getByText("Smoke Test Vendor Co.")).toBeVisible();
    await expect(page.getByText("Upload Documents")).toBeVisible();
  });

  test("4. Upload a DOCX file and trigger processing", async ({ page }) => {
    vendorCaseId = process.env._TEST_VENDOR_ID || vendorCaseId;
    if (!vendorCaseId) {
      test.skip(!vendorCaseId, "Vendor not created");
      return;
    }

    // Init upload via API
    const initRes = await page.request.post(
      `${API_BASE}/vendors/${vendorCaseId}/uploads/init`,
      {
        data: { filename: "sample.docx", doc_kind: "T&Cs" },
        headers: { "Content-Type": "application/json" },
      }
    );
    expect(initRes.ok()).toBeTruthy();
    const initData = await initRes.json();
    documentId = initData.document_id;
    process.env._TEST_DOC_ID = documentId;

    // Upload file bytes directly to presigned URL
    const fs = await import("fs");
    const fileBytes = fs.readFileSync(FIXTURE_DOCX);
    const uploadRes = await page.request.put(initData.upload_url, {
      data: fileBytes,
      headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document" },
    });
    expect(uploadRes.status()).toBeLessThan(300);

    // Complete upload
    const completeRes = await page.request.post(`${API_BASE}/uploads/complete`, {
      data: { document_id: documentId },
      headers: { "Content-Type": "application/json" },
    });
    expect(completeRes.ok()).toBeTruthy();
    const completeData = await completeRes.json();
    jobId = completeData.job_id;
    process.env._TEST_JOB_ID = jobId;

    expect(jobId).toBeTruthy();
    expect(documentId).toBeTruthy();
  });

  test("5. Wait for processing to complete", async ({ page }) => {
    jobId = process.env._TEST_JOB_ID || jobId;
    if (!jobId) {
      test.skip(!jobId, "Job not started");
      return;
    }
    await waitForJobDone(page, jobId, 120_000);
  });

  test("6. Review page loads and shows clause list", async ({ page }) => {
    vendorCaseId = process.env._TEST_VENDOR_ID || vendorCaseId;
    documentId = process.env._TEST_DOC_ID || documentId;
    if (!vendorCaseId || !documentId) {
      test.skip(true, "Upload not completed");
      return;
    }

    await page.goto(`/vendors/${vendorCaseId}/documents/${documentId}`);
    await expect(page.getByText("Document Review")).toBeVisible({ timeout: 30_000 });

    // Check for clause list items (at least 1 clause should be extracted)
    const clauseButtons = page.locator("button").filter({ hasText: /§|clause/i });
    await expect(clauseButtons.first()).toBeVisible({ timeout: 15_000 });
  });

  test("7. Admin precedents page loads", async ({ page }) => {
    await page.goto("/admin/precedents");
    await expect(page.getByRole("heading", { name: "Precedents" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Import CSV/i })).toBeVisible();
  });

  test("8. CSV import preview and import", async ({ page }) => {
    await page.goto("/admin/precedents");
    await page.getByRole("button", { name: /Import CSV/i }).click();

    // Upload CSV file
    await page.waitForSelector("input[type=file]");
    await page.locator("input[type=file]").setInputFiles(FIXTURE_CSV);

    // Wait for preview to load
    await expect(page.getByText(/valid rows/i)).toBeVisible({ timeout: 15_000 });
    await expect(page.getByText("3 valid rows")).toBeVisible();

    // Click import
    await page.getByRole("button", { name: /Import \d+ rows/i }).click();

    // Wait for completion
    await expect(page.getByText(/import complete/i)).toBeVisible({ timeout: 60_000 });
  });
});
