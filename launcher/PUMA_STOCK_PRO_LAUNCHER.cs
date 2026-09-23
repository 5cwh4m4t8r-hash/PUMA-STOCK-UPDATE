using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class PumaLauncher
{
    [STAThread]
    private static void Main()
    {
        try
        {
            string root = ResolveInstallRoot();
            if (String.IsNullOrWhiteSpace(root))
            {
                MessageBox.Show(
                    "PUMA 설치 위치를 찾지 못했습니다.\n\n먼저 PUMA를 설치 폴더에서 한 번 실행한 뒤 다시 시도하세요.",
                    "PUMA STOCK PRO",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning
                );
                return;
            }

            string pythonw = Path.Combine(root, "runtime", "pythonw.exe");
            string app = Path.Combine(root, "app.py");
            if (!File.Exists(pythonw) || !File.Exists(app))
            {
                MessageBox.Show(
                    "PUMA 실행 파일을 찾지 못했습니다.\n설치 폴더: " + root,
                    "PUMA STOCK PRO",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error
                );
                return;
            }

            var psi = new ProcessStartInfo
            {
                FileName = pythonw,
                Arguments = Quote(app),
                WorkingDirectory = root,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            Process.Start(psi);
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "PUMA STOCK PRO 실행 오류", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static string ResolveInstallRoot()
    {
        string marker = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "PUMA_STOCK_PRO",
            "install_path.txt"
        );

        if (File.Exists(marker))
        {
            string saved = File.ReadAllText(marker).Trim();
            if (IsPumaRoot(saved))
                return Path.GetFullPath(saved);
        }

        string beside = AppDomain.CurrentDomain.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        if (IsPumaRoot(beside))
            return beside;

        return "";
    }

    private static bool IsPumaRoot(string root)
    {
        if (String.IsNullOrWhiteSpace(root))
            return false;
        return File.Exists(Path.Combine(root, "app.py"))
            && File.Exists(Path.Combine(root, "runtime", "pythonw.exe"));
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}
