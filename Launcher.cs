using System;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Threading;

namespace SamVoiceStudio
{
    class Program
    {
        static Process serverProcess = null;

        static void Main(string[] args)
        {
            Console.OutputEncoding = System.Text.Encoding.UTF8;
            Console.Title = "SAM VOICE STUDIO — Local AI";
            Console.ForegroundColor = ConsoleColor.Cyan;

            Console.WriteLine(@"
==============================================================
   ███████╗ █████╗ ███╗   ███╗    ██╗   ██╗ ██████╗ ██╗ ██████╗███████╗
   ██╔════╝██╔══██╗████╗ ████║    ██║   ██║██╔═══██╗██║██╔════╝██╔════╝
   ███████╗███████║██╔████╔██║    ██║   ██║██║   ██║██║██║     █████╗  
   ╚════██║██╔══██║██║╚██╔╝██║    ╚██╗ ██╔╝██║   ██║██║██║     ██╔══╝  
   ███████║██║  ██║██║ ╚═╝ ██║     ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗
   ╚══════╝╚═╝  ╚═╝╚═╝     ╚═╝      ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝╚══════╝
                     STUDIO · LOCAL AI ENGINE
==============================================================");
            Console.ResetColor();

            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            Directory.SetCurrentDirectory(baseDir);

            // Locate python executable
            string pythonExe = null;
            string[] searchPaths = new string[]
            {
                Path.Combine(baseDir, "runtime", "python.exe"),
                Path.Combine(baseDir, ".venv", "Scripts", "python.exe"),
                Path.Combine(baseDir, "python_embed", "python.exe")
            };

            foreach (var p in searchPaths)
            {
                if (File.Exists(p))
                {
                    pythonExe = p;
                    break;
                }
            }

            if (string.IsNullOrEmpty(pythonExe))
            {
                // Fallback to system python
                pythonExe = "python.exe";
            }

            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("\n[1/3] جاري تشغيل خادم الذكاء الاصطناعي المحلي...");
            Console.ResetColor();

            // Setup process to start uvicorn
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = pythonExe;
            psi.Arguments = "-m uvicorn app:app --host 127.0.0.1 --port 8765";
            psi.WorkingDirectory = baseDir;
            psi.UseShellExecute = false;
            psi.CreateNoWindow = true;

            try
            {
                serverProcess = Process.Start(psi);
            }
            catch (Exception ex)
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("\n[خطأ] تعذر تشغيل بايثون: " + ex.Message);
                Console.WriteLine("تأكد من وجود مجلد runtime أو بايثون 3.11 على الجهاز.");
                Console.ResetColor();
                Console.WriteLine("\nاضغط أي مفتاح للخروج...");
                Console.ReadKey();
                return;
            }

            // Register cleanup on exit
            AppDomain.CurrentDomain.ProcessExit += (s, e) => Cleanup();
            Console.CancelKeyPress += (s, e) => { Cleanup(); };

            Console.ForegroundColor = ConsoleColor.Yellow;
            Console.WriteLine("[2/3] جاري فحص جاهزية الخادم ومكتبة النماذج...");
            Console.ResetColor();

            // Wait until http://127.0.0.1:8765/api/health is ready
            bool ready = false;
            for (int i = 0; i < 30; i++)
            {
                Thread.Sleep(800);
                try
                {
                    HttpWebRequest request = (HttpWebRequest)WebRequest.Create("http://127.0.0.1:8765/api/health");
                    request.Timeout = 1000;
                    using (HttpWebResponse response = (HttpWebResponse)request.GetResponse())
                    {
                        if (response.StatusCode == HttpStatusCode.OK)
                        {
                            ready = true;
                            break;
                        }
                    }
                }
                catch { }
            }

            if (ready)
            {
                Console.ForegroundColor = ConsoleColor.Green;
                Console.WriteLine("[3/3] تم الاتصال بالخادم بنجاح! جاري فتح المتصفح...");
                Console.ResetColor();

                string url = "http://127.0.0.1:8765";
                try
                {
                    Process.Start(new ProcessStartInfo(url) { UseShellExecute = true });
                }
                catch
                {
                    Console.WriteLine("افتح المتصفح على: " + url);
                }

                Console.ForegroundColor = ConsoleColor.White;
                Console.WriteLine("\n==============================================================");
                Console.WriteLine("  البرنامج يعمل الآن بنجاح على المتصفح: http://127.0.0.1:8765");
                Console.WriteLine("  اترك هذه النافذة مفتوحة طوال فترة عملك.");
                Console.WriteLine("  لإغلاق البرنامج بالكامل، اضغط مفتاح Enter أو أغلق هذه النافذة.");
                Console.WriteLine("==============================================================\n");
                Console.ResetColor();

                Console.ReadLine();
                Cleanup();
            }
            else
            {
                Console.ForegroundColor = ConsoleColor.Red;
                Console.WriteLine("\n[تنبيه] استغرق الخادم وقتاً أطول من المتوقع لبدء التشغيل.");
                Console.WriteLine("يمكنك محاولة فتح المتصفح يدوياً على: http://127.0.0.1:8765");
                Console.ResetColor();
                Console.WriteLine("\nاضغط أي مفتاح للخروج...");
                Console.ReadKey();
                Cleanup();
            }
        }

        static void Cleanup()
        {
            if (serverProcess != null && !serverProcess.HasExited)
            {
                try
                {
                    serverProcess.Kill();
                }
                catch { }
            }
        }
    }
}
