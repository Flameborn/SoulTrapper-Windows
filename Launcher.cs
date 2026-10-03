using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

class Launcher {
    static string Report(string folder, string details) {
        foreach (string location in new string[] {folder, Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "SoulTrapperWindows")}) {
            try {
                Directory.CreateDirectory(location);
                string path = Path.Combine(location, "error.log");
                File.AppendAllText(path, "\r\nSoul Trapper 1.0 launcher\r\n" + DateTime.UtcNow.ToString("o") + "\r\n" + Environment.OSVersion + "\r\n" + details + "\r\n", Encoding.UTF8);
                return path;
            } catch (IOException) {} catch (UnauthorizedAccessException) {}
        }
        return "The error log could not be written.";
    }
    [STAThread]
    static void Main(string[] args) {
        string folder = AppDomain.CurrentDomain.BaseDirectory;
        string root = Directory.Exists(Path.Combine(folder, "_internal")) ? Path.Combine(folder, "_internal") : folder;
        string python = Path.Combine(root, "runtime", "python.exe");
        string game = Path.Combine(root, "game.py");
        bool smoke = Array.IndexOf(args, "--smoke-test") >= 0;
        try {
            if (!File.Exists(python) || !File.Exists(game)) throw new FileNotFoundException("Extract the entire game ZIP. Keep the _internal folder beside Soul Trapper.exe.");
            var info = new ProcessStartInfo(python, "-E -s -X faulthandler -u \"" + game + "\"" + " --launcher" + (smoke ? " --smoke-test" : ""));
            info.WorkingDirectory = root;
            info.UseShellExecute = false;
            info.CreateNoWindow = true;
            info.RedirectStandardError = true;
            info.RedirectStandardOutput = true;
            var output = new StringBuilder();
            using (var process = new Process()) {
                process.StartInfo = info;
                DataReceivedEventHandler capture = delegate(object sender, DataReceivedEventArgs line) {
                    if (line.Data != null) lock(output) {
                        if(output.Length > 1000000) output.Remove(0, 500000);
                        output.AppendLine(line.Data);
                    }
                };
                process.ErrorDataReceived += capture;
                process.OutputDataReceived += capture;
                process.Start();
                process.BeginErrorReadLine();process.BeginOutputReadLine();
                process.WaitForExit();
                Environment.ExitCode = process.ExitCode;
                if (process.ExitCode != 0) {
                    string path = Report(folder, "Process exit code: " + process.ExitCode + " (0x" + unchecked((uint)process.ExitCode).ToString("X8") + ")\r\n" + output.ToString());
                    if (!smoke) MessageBox.Show("Soul Trapper closed unexpectedly. Please send error.log to the developer.\r\n\r\n" + path, "Soul Trapper");
                }
            }
        } catch (Exception e) {
            Environment.ExitCode = 1;
            string path = Report(folder, e.ToString());
            if (!smoke) MessageBox.Show("Soul Trapper could not start. Please send error.log to the developer.\r\n\r\n" + path, "Soul Trapper");
        }
    }
}
