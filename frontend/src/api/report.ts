import { api } from "./client";

/** 下载 AI 投研周报（自包含 HTML，blob 触发浏览器保存）。 */
export const downloadWeeklyReport = async (ai = true) => {
  const r = await api.get<Blob>("/report/weekly", {
    params: { ai },
    responseType: "blob",
  });
  const url = URL.createObjectURL(r.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = `tcalpha_weekly_${new Date().toISOString().slice(0, 10)}.html`;
  a.click();
  URL.revokeObjectURL(url);
};
