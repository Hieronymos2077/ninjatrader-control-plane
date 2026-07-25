using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Net;
using System.Text;
using System.Threading;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using NinjaTrader.Cbi;
using NinjaTrader.Data;
using NinjaTrader.Gui;
using NinjaTrader.Gui.Chart;
using NinjaTrader.NinjaScript;

namespace NinjaTrader.NinjaScript.AddOns
{
    public class AntigravityBridge : AddOnBase
    {
        private const int DefaultPort = 8089;
        private const string BridgeVersion = "2.0.0";

        private HttpListener _listener;
        private Thread _serverThread;
        private volatile bool _running;
        private int _port = DefaultPort;
        private readonly object _lock = new object();
        private Dispatcher _uiDispatcher;
        private readonly ConcurrentDictionary<string, Instrument> _marketDataSubscriptions =
            new ConcurrentDictionary<string, Instrument>(StringComparer.OrdinalIgnoreCase);

        protected override void OnStateChange()
        {
            if (State == State.SetDefaults)
            {
                Name = "Antigravity Bridge";
                Description = "HTTP API bridge for AI control of NinjaTrader 8";
            }
        }

        protected override void OnWindowCreated(Window window)
        {
            if (window is NinjaTrader.Gui.ControlCenter && !_running)
            {
                _uiDispatcher = window.Dispatcher;
                StartServer();
            }
        }

        protected override void OnWindowDestroyed(Window window)
        {
            if (window is NinjaTrader.Gui.ControlCenter)
                StopServer();
        }

        // ── Server lifecycle ─────────────────────────────────────────

        private void StartServer()
        {
            lock (_lock)
            {
                if (_running) return;
                _running = true;
            }

            _port = ResolvePort();

            _listener = new HttpListener();
            _listener.Prefixes.Add(string.Format("http://127.0.0.1:{0}/", _port));

            try
            {
                _listener.Start();
            }
            catch (HttpListenerException ex)
            {
                LogMessage(string.Format(
                    "Failed to start HTTP listener on port {0}: {1}. The port is likely already in use by another instance of the bridge or another application. Set a different port in {2}.",
                    _port, ex.Message, PortConfigPath()));
                _running = false;
                return;
            }
            catch (Exception ex)
            {
                LogMessage("Failed to start HTTP listener: " + ex.Message);
                _running = false;
                return;
            }

            _serverThread = new Thread(ListenLoop)
            {
                IsBackground = true,
                Name = "AntigravityBridge"
            };
            _serverThread.Start();
            LogMessage(string.Format("Antigravity Bridge started on port {0}", _port));
        }

        private static string PortConfigPath()
        {
            try
            {
                return Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "nt8bridge_port.txt");
            }
            catch
            {
                return "nt8bridge_port.txt";
            }
        }

        private static int ResolvePort()
        {
            int port = DefaultPort;
            try
            {
                string cfgPath = PortConfigPath();
                if (File.Exists(cfgPath))
                {
                    string text = File.ReadAllText(cfgPath).Trim();
                    int parsed;
                    if (int.TryParse(text, out parsed) && parsed > 0 && parsed <= 65535)
                        port = parsed;
                }
            }
            catch
            {
                port = DefaultPort;
            }
            return port;
        }

        private void StopServer()
        {
            lock (_lock)
            {
                if (!_running) return;
                _running = false;
            }

            try { _listener.Stop(); } catch { }
            try { _listener.Close(); } catch { }
            LogMessage("Antigravity Bridge stopped");
        }

        private void ListenLoop()
        {
            while (_running)
            {
                HttpListenerContext ctx;
                try
                {
                    ctx = _listener.GetContext();
                }
                catch
                {
                    if (!_running) break;
                    continue;
                }

                ThreadPool.QueueUserWorkItem(_ =>
                {
                    try
                    {
                        HandleRequest(ctx);
                    }
                    catch (Exception ex)
                    {
                        try
                        {
                            SendJson(ctx.Response, 500, ErrorJson(ex.Message));
                        }
                        catch { }
                    }
                });
            }
        }

        // ── Request routing ──────────────────────────────────────────

        private void HandleRequest(HttpListenerContext ctx)
        {
            var req = ctx.Request;
            var resp = ctx.Response;
            resp.Headers.Add("Access-Control-Allow-Origin", "*");

            if (req.HttpMethod == "OPTIONS")
            {
                resp.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
                resp.Headers.Add("Access-Control-Allow-Headers", "Content-Type");
                SendJson(resp, 200, "{}");
                return;
            }

            string path = req.Url.AbsolutePath.TrimEnd('/');
            string[] segments = path.Split(new[] { '/' }, StringSplitOptions.RemoveEmptyEntries);
            string body = null;

            if (req.HttpMethod == "POST" && req.HasEntityBody)
            {
                using (var reader = new StreamReader(req.InputStream, Encoding.UTF8))
                    body = reader.ReadToEnd();
            }

            string json;

            try
            {
                if (path == "/health")
                    json = HandleHealth();
                else if (path == "/version")
                    json = HandleVersion();
                else if (path == "/compile/probe")
                    json = HandleCompileProbe();
                else if (req.HttpMethod == "POST" && path == "/compile/trigger")
                    json = HandleCompileTrigger();
                else if (segments.Length == 3 && segments[0] == "account" && segments[2] == "state")
                    json = HandleAccountState(Uri.UnescapeDataString(segments[1]));
                else if (req.HttpMethod == "POST" && path == "/market-data/subscribe")
                    json = HandleSubscribeMarketData(body);
                else if (req.HttpMethod == "POST" && path == "/market-data/unsubscribe")
                    json = HandleUnsubscribeMarketData(body);
                else if (path == "/charts")
                    json = HandleGetCharts();
                else if (segments.Length == 3 && segments[0] == "chart" && segments[2] == "indicators")
                    json = HandleGetIndicators(segments[1]);
                else if (segments.Length == 4 && segments[0] == "chart" && segments[2] == "indicator" && segments[3] == "add")
                    json = HandleAddIndicator(segments[1], body);
                else if (segments.Length == 4 && segments[0] == "chart" && segments[2] == "indicator" && segments[3] == "remove")
                    json = HandleRemoveIndicator(segments[1], body);
                else if (segments.Length == 3 && segments[0] == "chart" && segments[2] == "screenshot")
                {
                    HandleScreenshot(segments[1], resp);
                    return;
                }
                else if (path == "/accounts")
                    json = HandleGetAccounts();
                else if (path == "/positions")
                    json = HandleGetPositions();
                else if (path == "/orders")
                    json = HandleGetOrders();
                else if (path == "/strategies")
                    json = HandleGetStrategies();
                else if (segments.Length == 2 && segments[0] == "market-data")
                    json = HandleGetMarketData(Uri.UnescapeDataString(segments[1]));
                else if (path == "/market-data/history")
                    json = HandleHistoricalBars(body);
                else if (path == "/connections")
                    json = HandleGetConnections();
                else if (path == "/logs/output")
                    json = HandleGetOutputLog();
                else if (req.HttpMethod == "POST" && segments.Length == 3 && segments[0] == "chart" && segments[2] == "close")
                    json = HandleCloseChart(segments[1]);
                else if (req.HttpMethod == "POST" && segments.Length == 4 && segments[0] == "chart" && segments[2] == "template" && segments[3] == "save")
                    json = HandleSaveTemplate(segments[1], body);
                else if (req.HttpMethod == "POST" && segments.Length == 4 && segments[0] == "chart" && segments[2] == "template" && segments[3] == "apply")
                    json = HandleApplyTemplate(segments[1], body);
                else if (req.HttpMethod == "POST" && path == "/strategy/attach")
                    json = HandleAttachStrategy(body);
                else if (req.HttpMethod == "POST" && path == "/strategy/detach")
                    json = HandleDetachStrategy(body);
                else if (segments.Length == 3 && segments[0] == "strategy" && segments[2] == "state")
                    json = HandleGetStrategyState(Uri.UnescapeDataString(segments[1]));
                else if (path == "/tester/status")
                    json = HandleGetTesterStatus();
                else if (path == "/tester/results")
                    json = HandleGetTesterResults();
                else
                {
                    SendJson(resp, 404, ErrorJson("Not found: " + path));
                    return;
                }

                SendJson(resp, 200, json);
            }
            catch (Exception ex)
            {
                SendJson(resp, 500, ErrorJson(ex.Message));
            }
        }

        // ── Route handlers ───────────────────────────────────────────

        private string HandleHealth()
        {
            int chartCount = 0;
            int accountCount = 0;

            RunOnUi(() =>
            {
                foreach (Window w in Application.Current.Windows)
                    if (w is Chart) chartCount++;
            });

            lock (Account.All)
                accountCount = Account.All.Count;

            var dict = new Dictionary<string, object>
            {
                { "ok", true },
                { "version", BridgeVersion },
                { "charts_count", chartCount },
                { "accounts_count", accountCount }
            };
            return ToJson(dict);
        }

        private string HandleVersion()
        {
            var dict = new Dictionary<string, object>
            {
                { "bridge_version", BridgeVersion },
                { "nt8_version", GetNt8Version() }
            };
            return ToJson(dict);
        }

        private static string GetNt8Version()
        {
            try
            {
                Type globalsType = typeof(NinjaTrader.Core.Globals);

                string[] propertyNames = { "ApplicationVersion", "AssemblyVersion", "Version" };
                foreach (string propName in propertyNames)
                {
                    var prop = globalsType.GetProperty(propName,
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                    if (prop == null) continue;
                    object val = prop.GetValue(null, null);
                    if (val != null) return val.ToString();
                }

                string[] fieldNames = { "ApplicationVersion", "AssemblyVersion", "Version" };
                foreach (string fieldName in fieldNames)
                {
                    var field = globalsType.GetField(fieldName,
                        System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Static);
                    if (field == null) continue;
                    object val = field.GetValue(null);
                    if (val != null) return val.ToString();
                }
            }
            catch
            {
                return "unknown";
            }
            return "unknown";
        }

        private string HandleGetCharts()
        {
            var items = new List<string>();

            RunOnUi(() =>
            {
                foreach (Window w in Application.Current.Windows)
                {
                    var chart = w as Chart;
                    if (chart == null) continue;

                    try
                    {
                        var cc = chart.ActiveChartControl;
                        if (cc == null || cc.BarsArray == null || cc.BarsArray.Length == 0) continue;

                        var bars = cc.BarsArray[0];
                        var dict = new Dictionary<string, object>
                        {
                            { "id", cc.GetHashCode().ToString() },
                            { "symbol", bars.Instrument != null ? bars.Instrument.FullName : "Unknown" },
                            { "period", cc.BarsPeriod != null ? cc.BarsPeriod.ToString() : "Unknown" },
                            { "bars_count", bars.Count },
                            { "title", w.Title ?? "" }
                        };
                        items.Add(ToJson(dict));
                    }
                    catch { }
                }
            });

            return "{\"charts\":[" + string.Join(",", items) + "]}";
        }

        private string HandleGetIndicators(string chartId)
        {
            var items = new List<string>();

            RunOnUi(() =>
            {
                var cc = FindChartControl(chartId);
                if (cc == null) return;

                try
                {
                    foreach (var ind in cc.Indicators)
                    {
                        var dict = new Dictionary<string, object>
                        {
                            { "name", ind.Name ?? "" },
                            { "type", ind.GetType().Name },
                            { "is_visible", ind.IsVisible }
                        };
                        items.Add(ToJson(dict));
                    }
                }
                catch { }
            });

            return "{\"indicators\":[" + string.Join(",", items) + "]}";
        }

        private string HandleAddIndicator(string chartId, string body)
        {
            string indicatorName = ParseJsonString(body, "name");
            if (string.IsNullOrEmpty(indicatorName))
                return ErrorJson("Missing 'name' in request body");

            bool success = false;
            string error = "";

            RunOnUi(() =>
            {
                try
                {
                    var cc = FindChartControl(chartId);
                    if (cc == null) { error = "Chart not found"; return; }

                    // Try to find indicator type in loaded assemblies
                    Type indicatorType = null;
                    foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                    {
                        indicatorType = asm.GetType("NinjaTrader.NinjaScript.Indicators." + indicatorName);
                        if (indicatorType != null) break;
                    }
                    if (indicatorType == null) { error = "Indicator type not found: " + indicatorName; return; }

                    // NOTE: Adding indicators programmatically is NOT officially supported by NinjaTrader.
                    // This uses reflection and may break with NT8 updates.
                    success = AddIndicatorToChart(cc, indicatorName);
                    if (!success)
                        error = "Indicator add via API is not reliably supported. Deploy indicator via NinjaScript code instead.";
                }
                catch (Exception ex)
                {
                    error = "Exception: " + ex.Message;
                }
            });

            if (success)
            {
                var dict = new Dictionary<string, object>
                {
                    { "ok", true },
                    { "indicator_name", indicatorName }
                };
                return ToJson(dict);
            }
            return ErrorJson(string.IsNullOrEmpty(error) ? "Failed to add indicator '" + indicatorName + "'" : error);
        }

        private string HandleRemoveIndicator(string chartId, string body)
        {
            string indicatorName = ParseJsonString(body, "name");
            int index = ParseJsonInt(body, "index", -1);

            bool success = false;

            RunOnUi(() =>
            {
                var cc = FindChartControl(chartId);
                if (cc == null) return;

                try
                {
                    if (index >= 0 && index < cc.Indicators.Count)
                    {
                        cc.Indicators.RemoveAt(index);
                        success = true;
                    }
                    else if (!string.IsNullOrEmpty(indicatorName))
                    {
                        var target = cc.Indicators.FirstOrDefault(
                            i => i.Name.Equals(indicatorName, StringComparison.OrdinalIgnoreCase));
                        if (target != null)
                        {
                            cc.Indicators.Remove(target);
                            success = true;
                        }
                    }
                }
                catch { }
            });

            if (success)
                return "{\"ok\":true}";
            return ErrorJson("Failed to remove indicator");
        }

        private void HandleScreenshot(string chartId, HttpListenerResponse resp)
        {
            byte[] png = null;
            string error = "";
            string captureMethod = "";

            RunOnUi(() =>
            {
                try
                {
                    Chart chart = FindChart(chartId);
                    if (chart == null) { error = "Chart not found"; return; }

                    // GetScreenshot is the primary, supported capture path. It can
                    // either return null (no throw) or throw depending on chart
                    // state, so both cases must fall through to the fallback below.
                    RenderTargetBitmap bmp = null;
                    try
                    {
                        bmp = chart.GetScreenshot(ShareScreenshotType.Window);
                    }
                    catch
                    {
                        bmp = null;
                    }

                    if (bmp != null)
                    {
                        captureMethod = "chart_get_screenshot";
                        var encoder = new PngBitmapEncoder();
                        encoder.Frames.Add(BitmapFrame.Create(bmp));
                        using (var ms = new MemoryStream())
                        {
                            encoder.Save(ms);
                            png = ms.ToArray();
                        }
                    }
                    else
                    {
                        // Fallback: render the chart control's WPF visual tree.
                        // NOTE (research 2026-07): this does NOT capture the
                        // SharpDX chart surface, so it can produce a blank or
                        // partial image. It exists only as a last resort when
                        // GetScreenshot fails; callers should check
                        // X-Capture-Method and treat this value as lower
                        // confidence than chart_get_screenshot.
                        var cc = chart.ActiveChartControl;
                        if (cc == null) { error = "No active chart control"; return; }
                        var rtb = new RenderTargetBitmap(
                            (int)cc.ActualWidth, (int)cc.ActualHeight, 96, 96,
                            PixelFormats.Pbgra32);
                        rtb.Render(cc);
                        captureMethod = "render_target_bitmap_fallback";
                        var encoder2 = new PngBitmapEncoder();
                        encoder2.Frames.Add(BitmapFrame.Create(rtb));
                        using (var ms = new MemoryStream())
                        {
                            encoder2.Save(ms);
                            png = ms.ToArray();
                        }
                    }
                }
                catch (Exception ex)
                {
                    error = "Screenshot failed: " + ex.Message;
                }
            });

            if (png != null && png.Length > 0)
            {
                // Save to temp file as well
                try
                {
                    string capturesDir = Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "captures");
                    Directory.CreateDirectory(capturesDir);
                    string filePath = Path.Combine(capturesDir,
                        "screenshot_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".png");
                    File.WriteAllBytes(filePath, png);
                }
                catch { }

                resp.Headers.Add("X-Capture-Method", captureMethod);
                resp.ContentType = "image/png";
                resp.ContentLength64 = png.Length;
                resp.StatusCode = 200;
                resp.OutputStream.Write(png, 0, png.Length);
                resp.OutputStream.Close();
            }
            else
            {
                SendJson(resp, 500, ErrorJson(
                    string.IsNullOrEmpty(error) ? "Screenshot capture returned empty" : error));
            }
        }

        private string HandleGetAccounts()
        {
            var items = new List<string>();
            double totalBuyingPower = 0;
            double totalCashValue = 0;
            double totalRealizedPnl = 0;
            double totalUnrealizedPnl = 0;
            int accountCount = 0;

            lock (Account.All)
            {
                foreach (Account a in Account.All)
                {
                    try
                    {
                        double buyingPower = ToDouble(SafeGet(a, AccountItem.BuyingPower));
                        double cashValue = ToDouble(SafeGet(a, AccountItem.CashValue));
                        double realizedPnl = ToDouble(SafeGet(a, AccountItem.RealizedProfitLoss));
                        double unrealizedPnl = ToDouble(SafeGet(a, AccountItem.UnrealizedProfitLoss));

                        var dict = new Dictionary<string, object>
                        {
                            { "name", a.Name ?? "" },
                            { "connection", a.Connection != null && a.Connection.Options != null ? a.Connection.Options.Name : "" },
                            { "buying_power", buyingPower },
                            { "cash_value", cashValue },
                            { "realized_pnl", realizedPnl },
                            { "unrealized_pnl", unrealizedPnl }
                        };
                        items.Add(ToJson(dict));

                        totalBuyingPower += buyingPower;
                        totalCashValue += cashValue;
                        totalRealizedPnl += realizedPnl;
                        totalUnrealizedPnl += unrealizedPnl;
                        accountCount++;
                    }
                    catch { }
                }
            }

            var totals = new Dictionary<string, object>
            {
                { "account_count", accountCount },
                { "buying_power", totalBuyingPower },
                { "cash_value", totalCashValue },
                { "realized_pnl", totalRealizedPnl },
                { "unrealized_pnl", totalUnrealizedPnl }
            };

            return "{\"accounts\":[" + string.Join(",", items) + "],\"totals\":" + ToJson(totals) + "}";
        }

        private string HandleAccountState(string accountName)
        {
            Account target = FindAccountByName(accountName);
            if (target == null)
                return ErrorJson("Account not found: " + accountName);

            try
            {
                int positionCount = 0;
                int orderCount = 0;
                try { positionCount = target.Positions.Count(p => p.MarketPosition != MarketPosition.Flat); }
                catch { }
                try { orderCount = target.Orders.Count(); }
                catch { }

                var dict = new Dictionary<string, object>
                {
                    { "name", target.Name ?? "" },
                    { "buying_power", ToDouble(SafeGet(target, AccountItem.BuyingPower)) },
                    { "cash_value", ToDouble(SafeGet(target, AccountItem.CashValue)) },
                    { "net_liquidation", ToDouble(SafeGet(target, AccountItem.NetLiquidation)) },
                    { "realized_pnl", ToDouble(SafeGet(target, AccountItem.RealizedProfitLoss)) },
                    { "unrealized_pnl", ToDouble(SafeGet(target, AccountItem.UnrealizedProfitLoss)) },
                    { "position_count", positionCount },
                    { "order_count", orderCount }
                };
                return ToJson(dict);
            }
            catch (Exception ex)
            {
                return ErrorJson("Failed to read account state: " + ex.Message);
            }
        }

        private static Account FindAccountByName(string accountName)
        {
            lock (Account.All)
            {
                foreach (Account a in Account.All)
                {
                    if (a.Name != null && a.Name.Equals(accountName, StringComparison.OrdinalIgnoreCase))
                        return a;
                }
            }
            return null;
        }

        private static object SafeGet(Account a, AccountItem item)
        {
            try { return a.Get(item, Currency.UsDollar); }
            catch { return null; }
        }

        private static double ToDouble(object val)
        {
            if (val == null) return 0.0;
            try { return Convert.ToDouble(val, CultureInfo.InvariantCulture); }
            catch { return 0.0; }
        }

        private string HandleGetPositions()
        {
            var items = new List<string>();

            lock (Account.All)
            {
                foreach (Account a in Account.All)
                {
                    try
                    {
                        foreach (var pos in a.Positions)
                        {
                            var dict = new Dictionary<string, object>
                            {
                                { "account", a.Name ?? "" },
                                { "instrument", pos.Instrument != null ? pos.Instrument.FullName : "" },
                                { "direction", pos.MarketPosition.ToString() },
                                { "quantity", pos.Quantity },
                                { "avg_entry", pos.AveragePrice },
                                { "unrealized_pnl", pos.GetUnrealizedProfitLoss(PerformanceUnit.Currency) }
                            };
                            items.Add(ToJson(dict));
                        }
                    }
                    catch { }
                }
            }

            return "{\"positions\":[" + string.Join(",", items) + "]}";
        }

        private string HandleGetOrders()
        {
            var items = new List<string>();

            lock (Account.All)
            {
                foreach (Account a in Account.All)
                {
                    try
                    {
                        foreach (var order in a.Orders)
                        {
                            var dict = new Dictionary<string, object>
                            {
                                { "account", a.Name ?? "" },
                                { "order_id", order.OrderId ?? "" },
                                { "instrument", order.Instrument != null ? order.Instrument.FullName : "" },
                                { "action", order.OrderAction.ToString() },
                                { "type", order.OrderType.ToString() },
                                { "quantity", order.Quantity },
                                { "limit_price", order.LimitPrice },
                                { "stop_price", order.StopPrice },
                                { "state", order.OrderState.ToString() },
                                { "filled", order.Filled },
                                { "avg_fill_price", order.AverageFillPrice },
                                { "tif", order.TimeInForce.ToString() }
                            };
                            items.Add(ToJson(dict));
                        }
                    }
                    catch { }
                }
            }

            return "{\"orders\":[" + string.Join(",", items) + "]}";
        }

        private string HandleGetStrategies()
        {
            var items = new List<string>();

            try
            {
                lock (Account.All)
                {
                    foreach (Account account in Account.All)
                    {
                        try
                        {
                            lock (account.Strategies)
                            {
                                foreach (StrategyBase strategy in account.Strategies)
                                {
                                    var dict = new Dictionary<string, object>
                                    {
                                        { "name", strategy.Name ?? "" },
                                        { "state", strategy.State.ToString() },
                                        { "account", account.Name ?? "" },
                                        { "instrument", strategy.Instrument != null ? strategy.Instrument.FullName : "" },
                                        { "position", strategy.Position != null ? strategy.Position.MarketPosition.ToString() : "Flat" },
                                        { "unrealized_pnl", strategy.Position != null ? strategy.Position.GetUnrealizedProfitLoss(PerformanceUnit.Currency) : 0.0 }
                                    };
                                    items.Add(ToJson(dict));
                                }
                            }
                        }
                        catch { }
                    }
                }
            }
            catch { }

            return "{\"strategies\":[" + string.Join(",", items) + "]}";
        }

        private string HandleGetMarketData(string instrument)
        {
            Instrument inst = null;

            try
            {
                inst = Instrument.GetInstrument(instrument);
            }
            catch { }

            if (inst == null)
                return ErrorJson("Instrument not found: " + instrument);

            var mdf = inst.MarketData;
            if (mdf == null)
                return ErrorJson("No market data for: " + instrument);

            var dict = new Dictionary<string, object>
            {
                { "instrument", inst.FullName },
                { "last", mdf.Last != null ? (object)mdf.Last.Price : null },
                { "bid", mdf.Bid != null ? (object)mdf.Bid.Price : null },
                { "ask", mdf.Ask != null ? (object)mdf.Ask.Price : null },
                { "volume", mdf.Last != null ? (object)mdf.Last.Volume : null },
                { "daily_high", mdf.DailyHigh != null ? (object)mdf.DailyHigh.Price : null },
                { "daily_low", mdf.DailyLow != null ? (object)mdf.DailyLow.Price : null }
            };
            return ToJson(dict);
        }

        private string HandleSubscribeMarketData(string body)
        {
            string instrumentName = ParseJsonString(body, "instrument");
            if (string.IsNullOrEmpty(instrumentName))
                return ErrorJson("Missing 'instrument' in request body");

            try
            {
                Instrument inst = Instrument.GetInstrument(instrumentName);
                if (inst == null)
                    return ErrorJson("Instrument not found: " + instrumentName);

                bool alreadySubscribed = _marketDataSubscriptions.ContainsKey(inst.FullName);
                if (!alreadySubscribed)
                {
                    inst.MarketData.Update += OnMarketDataUpdate;
                    _marketDataSubscriptions[inst.FullName] = inst;
                }

                var dict = new Dictionary<string, object>
                {
                    { "ok", true },
                    { "instrument", inst.FullName },
                    { "already_subscribed", alreadySubscribed }
                };
                return ToJson(dict);
            }
            catch (Exception ex)
            {
                return ErrorJson("Subscribe failed: " + ex.Message);
            }
        }

        private string HandleUnsubscribeMarketData(string body)
        {
            string instrumentName = ParseJsonString(body, "instrument");
            if (string.IsNullOrEmpty(instrumentName))
                return ErrorJson("Missing 'instrument' in request body");

            bool found = false;
            string resolvedName = instrumentName;

            try
            {
                Instrument inst = Instrument.GetInstrument(instrumentName);
                string key = inst != null ? inst.FullName : instrumentName;
                resolvedName = key;

                Instrument removed;
                if (_marketDataSubscriptions.TryRemove(key, out removed))
                {
                    try { removed.MarketData.Update -= OnMarketDataUpdate; }
                    catch { }
                    found = true;
                }
            }
            catch { }

            var dict = new Dictionary<string, object>
            {
                { "ok", found },
                { "instrument", resolvedName },
                { "was_subscribed", found }
            };
            return ToJson(dict);
        }

        // Subscribing Instrument.MarketData.Update activates the live feed for
        // that instrument so HandleGetMarketData (GET /market-data/{instrument})
        // can serve fresh values even without an open chart. No per tick
        // processing is needed in this handler itself.
        private void OnMarketDataUpdate(object sender, MarketDataEventArgs e)
        {
        }

        private string HandleHistoricalBars(string body)
        {
            string instrument = ParseJsonString(body, "instrument");
            if (string.IsNullOrEmpty(instrument))
                return ErrorJson("Missing 'instrument'");

            int barsBack = ParseJsonInt(body, "bars_back", 100);

            var items = new List<string>();

            RunOnUi(() =>
            {
                try
                {
                    foreach (Window w in Application.Current.Windows)
                    {
                        var chart = w as Chart;
                        if (chart == null) continue;

                        var cc = chart.ActiveChartControl;
                        if (cc == null || cc.BarsArray == null || cc.BarsArray.Length == 0) continue;

                        var bars = cc.BarsArray[0];
                        if (bars.Instrument == null) continue;
                        if (!bars.Instrument.FullName.Equals(instrument, StringComparison.OrdinalIgnoreCase))
                            continue;

                        int start = Math.Max(0, bars.Count - barsBack);
                        for (int i = start; i < bars.Count; i++)
                        {
                            var dict = new Dictionary<string, object>
                            {
                                { "time", bars.GetTime(i).ToString("o") },
                                { "open", bars.GetOpen(i) },
                                { "high", bars.GetHigh(i) },
                                { "low", bars.GetLow(i) },
                                { "close", bars.GetClose(i) },
                                { "volume", bars.GetVolume(i) }
                            };
                            items.Add(ToJson(dict));
                        }
                        break;
                    }
                }
                catch { }
            });

            return "{\"bars\":[" + string.Join(",", items) + "]}";
        }

        private string HandleGetConnections()
        {
            var items = new List<string>();

            try
            {
                foreach (var conn in Connection.Connections)
                {
                    var dict = new Dictionary<string, object>
                    {
                        { "name", conn.Options != null ? conn.Options.Name : "Unknown" },
                        { "status", conn.Status.ToString() },
                        { "provider", conn.Options != null ? conn.Options.Provider.ToString() : "" }
                    };
                    items.Add(ToJson(dict));
                }
            }
            catch { }

            return "{\"connections\":[" + string.Join(",", items) + "]}";
        }

        // ── Compile diagnostics (experimental) ───────────────────────
        //
        // There is no supported programmatic compile API in NinjaTrader 8
        // (staff confirmed, ticket SFT thread 1215609). These two routes are
        // best effort reflection diagnostics kept behind try/catch so they
        // can never crash NT8. The supported compile path remains the
        // keyboard backend sending F5 in the NinjaScript Editor.

        private string HandleCompileProbe()
        {
            var items = new List<string>();

            try
            {
                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    Type[] types;
                    try { types = asm.GetTypes(); }
                    catch { continue; }

                    foreach (var t in types)
                    {
                        try
                        {
                            if (t.Name == null || t.Name.IndexOf("Compil", StringComparison.OrdinalIgnoreCase) < 0)
                                continue;

                            var methodNames = new List<string>();
                            var methods = t.GetMethods(
                                System.Reflection.BindingFlags.Public |
                                System.Reflection.BindingFlags.NonPublic |
                                System.Reflection.BindingFlags.Static |
                                System.Reflection.BindingFlags.DeclaredOnly);

                            foreach (var m in methods)
                            {
                                try
                                {
                                    var paramList = new List<string>();
                                    foreach (var p in m.GetParameters())
                                        paramList.Add(p.ParameterType.Name + " " + p.Name);
                                    methodNames.Add(m.Name + "(" + string.Join(", ", paramList) + ") : " + m.ReturnType.Name);
                                }
                                catch { }
                            }

                            var methodJson = new List<string>();
                            foreach (var n in methodNames)
                                methodJson.Add("\"" + EscapeJson(n) + "\"");

                            var dict = new Dictionary<string, object>
                            {
                                { "assembly", asm.GetName().Name },
                                { "type", t.FullName ?? t.Name },
                                { "static_methods", new RawJson("[" + string.Join(",", methodJson) + "]") }
                            };
                            items.Add(ToJson(dict));
                        }
                        catch { }
                    }
                }
            }
            catch { }

            return "{\"ok\":true,\"experimental\":true,\"candidates\":[" + string.Join(",", items) + "]}";
        }

        private string HandleCompileTrigger()
        {
            try
            {
                System.Reflection.MethodInfo candidate = null;
                Type ownerType = null;

                foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                {
                    Type[] types;
                    try { types = asm.GetTypes(); }
                    catch { continue; }

                    foreach (var t in types)
                    {
                        if (t.Namespace == null) continue;
                        if (t.Namespace.IndexOf("NinjaTrader.NinjaScript", StringComparison.OrdinalIgnoreCase) < 0 &&
                            t.Namespace.IndexOf("NinjaTrader.Code", StringComparison.OrdinalIgnoreCase) < 0)
                            continue;

                        System.Reflection.MethodInfo[] methods;
                        try
                        {
                            methods = t.GetMethods(
                                System.Reflection.BindingFlags.Public |
                                System.Reflection.BindingFlags.NonPublic |
                                System.Reflection.BindingFlags.Static);
                        }
                        catch { continue; }

                        foreach (var m in methods)
                        {
                            if (m.Name != "Compile" && m.Name != "CompileAsync") continue;
                            var ps = m.GetParameters();
                            if (ps.Length == 0 ||
                                (ps.Length == 1 && (ps[0].ParameterType == typeof(bool) || ps[0].ParameterType == typeof(string))))
                            {
                                candidate = m;
                                ownerType = t;
                                break;
                            }
                        }
                        if (candidate != null) break;
                    }
                    if (candidate != null) break;
                }

                if (candidate == null)
                {
                    var noneDict = new Dictionary<string, object>
                    {
                        { "attempted", false },
                        { "reason", "No safe zero arg or simple arg Compile or CompileAsync method was found on any loaded NinjaTrader.NinjaScript or NinjaTrader.Code type. This route is experimental. The supported compile path is the keyboard backend sending F5 in the NinjaScript Editor." },
                        { "experimental", true }
                    };
                    return ToJson(noneDict);
                }

                string methodDesc = (ownerType != null ? ownerType.FullName : "") + "." + candidate.Name;
                var parameters = candidate.GetParameters();
                object[] callArgs;
                if (parameters.Length == 0)
                    callArgs = new object[0];
                else if (parameters[0].ParameterType == typeof(bool))
                    callArgs = new object[] { false };
                else
                    callArgs = new object[] { null };

                object invokeResult = null;
                bool threw = false;
                string exceptionMessage = "";

                var invokeThread = new Thread(() =>
                {
                    try
                    {
                        invokeResult = candidate.Invoke(null, callArgs);
                    }
                    catch (Exception ex)
                    {
                        threw = true;
                        exceptionMessage = ex.Message;
                    }
                });
                invokeThread.IsBackground = true;
                invokeThread.Start();
                invokeThread.Join(TimeSpan.FromSeconds(60));

                string resultDesc;
                if (invokeThread.IsAlive)
                    resultDesc = "Invocation exceeded the 60s guard and is still running in the background. Result unknown, treat as unverified.";
                else if (threw)
                    resultDesc = "Invocation threw: " + exceptionMessage;
                else
                    resultDesc = invokeResult != null ? invokeResult.ToString() : "Invoked, no return value";

                var dict = new Dictionary<string, object>
                {
                    { "attempted", true },
                    { "method", methodDesc },
                    { "result", resultDesc },
                    { "experimental", true }
                };
                return ToJson(dict);
            }
            catch (Exception ex)
            {
                var errDict = new Dictionary<string, object>
                {
                    { "attempted", false },
                    { "reason", "Unexpected error while probing for a compile entry point: " + ex.Message },
                    { "experimental", true }
                };
                return ToJson(errDict);
            }
        }

        private string HandleGetOutputLog()
        {
            string logDir = Path.Combine(NinjaTrader.Core.Globals.UserDataDir, "log");
            if (!Directory.Exists(logDir))
                return ErrorJson("Log directory not found");

            var logFiles = Directory.GetFiles(logDir, "*.log")
                .OrderByDescending(f => File.GetLastWriteTime(f))
                .ToArray();

            if (logFiles.Length == 0)
                return ErrorJson("No log files found");

            string content = "";
            string logFile = logFiles[0];
            int totalLines = 0;
            try
            {
                var lines = File.ReadAllLines(logFile);
                totalLines = lines.Length;
                int start = Math.Max(0, lines.Length - 200);
                content = string.Join("\n", lines.Skip(start));
            }
            catch (Exception ex)
            {
                return ErrorJson("Failed to read log: " + ex.Message);
            }

            var dict = new Dictionary<string, object>
            {
                { "log_file", logFile },
                { "text", content },
                { "total_lines", totalLines }
            };
            return ToJson(dict);
        }

        private string HandleCloseChart(string chartId)
        {
            bool success = false;
            RunOnUi(() =>
            {
                var chart = FindChart(chartId);
                if (chart != null)
                {
                    chart.Close();
                    success = true;
                }
            });
            if (success)
                return "{\"ok\":true,\"message\":\"Chart closed\"}";
            return ErrorJson("Chart not found");
        }

        private string HandleSaveTemplate(string chartId, string body)
        {
            return NotSupportedJson(
                "Chart template save is not exposed by a supported NinjaTrader 8 AddOn API. Confirmed platform gap, ticket SFT-1445.",
                "Use the NT8 GUI: right click the chart, Templates, Save As. Automate the click sequence via the keyboard backend if a scripted flow is required.");
        }

        private string HandleApplyTemplate(string chartId, string body)
        {
            return NotSupportedJson(
                "Chart template apply is not exposed by a supported NinjaTrader 8 AddOn API. Confirmed platform gap, ticket SFT-1445.",
                "Use the NT8 GUI: right click the chart, Templates, select the template. Automate the click sequence via the keyboard backend if a scripted flow is required.");
        }

        private string HandleAttachStrategy(string body)
        {
            return NotSupportedJson(
                "Enabling a strategy from an AddOn is not exposed by a supported NinjaTrader 8 API. Confirmed platform gap, ticket SFT-977.",
                "Use the NT8 GUI: right click the chart, Strategies, Add Strategy. Alternatively set IsEnabled = true in the strategy's State.SetDefaults so it auto enables when its workspace loads.");
        }

        private string HandleDetachStrategy(string body)
        {
            return NotSupportedJson(
                "Disabling a strategy from an AddOn is not exposed by a supported NinjaTrader 8 API. Confirmed platform gap, ticket SFT-977.",
                "Use the NT8 GUI: right click the chart, Strategies, remove the strategy, or uncheck Enabled in the strategy's properties.");
        }

        private string HandleGetStrategyState(string strategyName)
        {
            var items = new List<string>();

            try
            {
                lock (Account.All)
                {
                    foreach (Account account in Account.All)
                    {
                        try
                        {
                            lock (account.Strategies)
                            {
                                foreach (StrategyBase strategy in account.Strategies)
                                {
                                    if (strategy.Name != null && strategy.Name.Equals(strategyName, StringComparison.OrdinalIgnoreCase))
                                    {
                                        var dict = new Dictionary<string, object>
                                        {
                                            { "name", strategy.Name ?? "" },
                                            { "state", strategy.State.ToString() },
                                            { "account", account.Name ?? "" },
                                            { "instrument", strategy.Instrument != null ? strategy.Instrument.FullName : "" },
                                            { "position", strategy.Position != null ? strategy.Position.MarketPosition.ToString() : "Flat" },
                                            { "unrealized_pnl", strategy.Position != null ? strategy.Position.GetUnrealizedProfitLoss(PerformanceUnit.Currency) : 0.0 }
                                        };
                                        items.Add(ToJson(dict));
                                    }
                                }
                            }
                        }
                        catch { }
                    }
                }
            }
            catch { }

            if (items.Count == 0)
                return ErrorJson("Strategy not found: " + strategyName);
            return items[0];
        }

        private string HandleGetTesterStatus()
        {
            return NotSupportedJson(
                "Strategy Analyzer status is not exposed by a supported NinjaTrader 8 AddOn API. No headless backtest interface exists (ticket SFT-4391).",
                "Use the file based mechanism: poll Documents\\NinjaTrader 8\\strategyanalyzerlogs for a new xml file created after the run started (file_write backend, action analyzer_status).");
        }

        private string HandleGetTesterResults()
        {
            return NotSupportedJson(
                "Strategy Analyzer results are not exposed by a supported NinjaTrader 8 AddOn API. No headless backtest interface exists (ticket SFT-4391).",
                "Use the file based mechanism: parse the newest xml in Documents\\NinjaTrader 8\\strategyanalyzerlogs (file_write backend, action analyzer_results) for SummaryPerformances stats.");
        }

        // ── Chart lookup helpers ─────────────────────────────────────

        private ChartControl FindChartControl(string chartId)
        {
            ChartControl result = null;

            foreach (Window w in Application.Current.Windows)
            {
                var chart = w as Chart;
                if (chart == null) continue;

                var cc = chart.ActiveChartControl;
                if (cc == null) continue;

                // "active" means return the first chart found (typically the focused one)
                if (chartId == "active" || cc.GetHashCode().ToString() == chartId)
                {
                    result = cc;
                    break;
                }
            }

            return result;
        }

        private Chart FindChart(string chartId)
        {
            foreach (Window w in Application.Current.Windows)
            {
                var chart = w as Chart;
                if (chart == null) continue;

                var cc = chart.ActiveChartControl;
                if (cc == null) continue;

                if (chartId == "active" || cc.GetHashCode().ToString() == chartId)
                    return chart;
            }
            return null;
        }

        // ── Indicator management ─────────────────────────────────────

        private bool AddIndicatorToChart(ChartControl cc, string indicatorName)
        {
            try
            {
                var indicatorType = Type.GetType(
                    string.Format("NinjaTrader.NinjaScript.Indicators.{0}", indicatorName));

                if (indicatorType == null)
                {
                    // Search all loaded assemblies
                    foreach (var asm in AppDomain.CurrentDomain.GetAssemblies())
                    {
                        indicatorType = asm.GetType(
                            string.Format("NinjaTrader.NinjaScript.Indicators.{0}", indicatorName));
                        if (indicatorType != null) break;
                    }
                }

                if (indicatorType == null) return false;

                var indicator = (IndicatorBase)Activator.CreateInstance(indicatorType);
                indicator.SetState(State.SetDefaults);

                cc.Indicators.Add(indicator);

                var refreshMethod = cc.GetType().GetMethod("RefreshIndicators",
                    System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance);
                if (refreshMethod != null)
                    refreshMethod.Invoke(cc, new object[] { true, true });

                return true;
            }
            catch
            {
                return false;
            }
        }

        // ── UI thread helper ─────────────────────────────────────────

        private void RunOnUi(Action action)
        {
            if (_uiDispatcher == null) return;

            if (_uiDispatcher.CheckAccess())
            {
                action();
            }
            else
            {
                _uiDispatcher.Invoke(action, DispatcherPriority.Normal,
                    CancellationToken.None, TimeSpan.FromSeconds(10));
            }
        }

        // ── JSON helpers (zero-dependency) ───────────────────────────

        // Wraps a pre-formatted JSON fragment (array or object) so ToJson
        // embeds it verbatim instead of quoting it as a string.
        private sealed class RawJson
        {
            public readonly string Json;
            public RawJson(string json) { Json = json; }
        }

        private static string ToJson(Dictionary<string, object> dict)
        {
            var sb = new StringBuilder("{");
            bool first = true;
            foreach (var kv in dict)
            {
                if (!first) sb.Append(",");
                sb.Append("\"");
                sb.Append(EscapeJson(kv.Key));
                sb.Append("\":");
                sb.Append(FormatValue(kv.Value));
                first = false;
            }
            sb.Append("}");
            return sb.ToString();
        }

        private static string FormatValue(object val)
        {
            if (val == null) return "null";
            if (val is RawJson) return ((RawJson)val).Json;
            if (val is bool) return ((bool)val) ? "true" : "false";
            if (val is string) return "\"" + EscapeJson((string)val) + "\"";
            if (val is double) return ((double)val).ToString("G", CultureInfo.InvariantCulture);
            if (val is float) return ((float)val).ToString("G", CultureInfo.InvariantCulture);
            if (val is decimal) return ((decimal)val).ToString("G", CultureInfo.InvariantCulture);
            if (val is int) return ((int)val).ToString();
            if (val is long) return ((long)val).ToString();
            return "\"" + EscapeJson(val.ToString()) + "\"";
        }

        private static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return "";
            var sb = new StringBuilder(s.Length);
            foreach (char c in s)
            {
                switch (c)
                {
                    case '"': sb.Append("\\\""); break;
                    case '\\': sb.Append("\\\\"); break;
                    case '\b': sb.Append("\\b"); break;
                    case '\f': sb.Append("\\f"); break;
                    case '\n': sb.Append("\\n"); break;
                    case '\r': sb.Append("\\r"); break;
                    case '\t': sb.Append("\\t"); break;
                    default:
                        if (c < 0x20)
                            sb.AppendFormat("\\u{0:x4}", (int)c);
                        else
                            sb.Append(c);
                        break;
                }
            }
            return sb.ToString();
        }

        private static string ErrorJson(string message)
        {
            return "{\"ok\":false,\"error\":\"" + EscapeJson(message) + "\"}";
        }

        // Confirmed NT8 platform gaps (no supported AddOn API exists) return
        // HTTP 200 with ok=false, error_code NOT_SUPPORTED_BY_PLATFORM and a
        // remediation hint. Honest failure, never a silent stub.
        private static string NotSupportedJson(string message, string remediation)
        {
            var dict = new Dictionary<string, object>
            {
                { "ok", false },
                { "error", message },
                { "error_code", "NOT_SUPPORTED_BY_PLATFORM" },
                { "remediation", remediation }
            };
            return ToJson(dict);
        }

        private static string ParseJsonString(string json, string key)
        {
            if (string.IsNullOrEmpty(json)) return null;

            string search = "\"" + key + "\"";
            int idx = json.IndexOf(search, StringComparison.Ordinal);
            if (idx < 0) return null;

            idx = json.IndexOf(':', idx + search.Length);
            if (idx < 0) return null;

            idx++;
            while (idx < json.Length && json[idx] == ' ') idx++;
            if (idx >= json.Length || json[idx] != '"') return null;

            idx++;
            var sb = new StringBuilder();
            while (idx < json.Length && json[idx] != '"')
            {
                if (json[idx] == '\\' && idx + 1 < json.Length)
                {
                    idx++;
                    sb.Append(json[idx]);
                }
                else
                {
                    sb.Append(json[idx]);
                }
                idx++;
            }
            return sb.ToString();
        }

        private static int ParseJsonInt(string json, string key, int defaultVal)
        {
            if (string.IsNullOrEmpty(json)) return defaultVal;

            string search = "\"" + key + "\"";
            int idx = json.IndexOf(search, StringComparison.Ordinal);
            if (idx < 0) return defaultVal;

            idx = json.IndexOf(':', idx + search.Length);
            if (idx < 0) return defaultVal;

            idx++;
            while (idx < json.Length && json[idx] == ' ') idx++;

            var sb = new StringBuilder();
            while (idx < json.Length && (char.IsDigit(json[idx]) || json[idx] == '-'))
            {
                sb.Append(json[idx]);
                idx++;
            }

            int result;
            return int.TryParse(sb.ToString(), out result) ? result : defaultVal;
        }

        // ── HTTP response helper ─────────────────────────────────────

        private static void SendJson(HttpListenerResponse resp, int statusCode, string json)
        {
            resp.StatusCode = statusCode;
            resp.ContentType = "application/json; charset=utf-8";
            byte[] buf = Encoding.UTF8.GetBytes(json);
            resp.ContentLength64 = buf.Length;
            resp.OutputStream.Write(buf, 0, buf.Length);
            resp.OutputStream.Close();
        }

        // ── Logging ──────────────────────────────────────────────────

        private void LogMessage(string msg)
        {
            try
            {
                NinjaTrader.Code.Output.Process(
                    string.Format("[AntigravityBridge] {0}", msg), PrintTo.OutputTab1);
            }
            catch { }
        }
    }
}
