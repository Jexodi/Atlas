using System.IO.Pipes;
using System.Text;
using System.Text.Json;

namespace Sideron.UI.Services;

public sealed class SideronIpcServerService
    : IDisposable
{
    public const string CoreToUiPipeName =
        "SIDERON.CoreToUI.v1";

    public const string UiToCorePipeName =
        "Sideron.UIToCore.v1";

    private readonly object _sync =
        new();

    private readonly SemaphoreSlim _sendLock =
        new(
            1,
            1);

    private CancellationTokenSource?
        _cancellation;

    private NamedPipeServerStream?
        _coreToUiServer;

    private NamedPipeServerStream?
        _uiToCoreServer;

    private StreamWriter?
        _toCoreWriter;

    private Task?
        _serverTask;

    private bool _connected;

    public event Action<bool>?
        ConnectionChanged;

    public event Action<JsonElement>?
        MessageReceived;

    public bool IsConnected
    {
        get
        {
            lock (_sync)
            {
                return _connected;
            }
        }
    }

    public void Start()
    {
        lock (_sync)
        {
            if (
                _serverTask is not null
                && !_serverTask.IsCompleted
            )
            {
                return;
            }

            _cancellation =
                new CancellationTokenSource();

            _serverTask =
                Task.Run(
                    () =>
                        RunServerAsync(
                            _cancellation.Token));
        }
    }

    public async Task<bool> SendCommandAsync(
        string name,
        object? payload = null)
    {
        var sent =
            await SendAsync(
                new
                {
                    type = "command",
                    name,
                    payload,
                });

        UiLog.Info(
            $"IPC Sideron.UI -> Core: command={name}, sent={sent}");

        return sent;
    }

    private async Task RunServerAsync(
        CancellationToken cancellationToken)
    {
        while (
            !cancellationToken
                .IsCancellationRequested
        )
        {
            NamedPipeServerStream?
                coreToUi = null;

            NamedPipeServerStream?
                uiToCore = null;

            try
            {
                coreToUi =
                    CreatePipe(
                        CoreToUiPipeName,
                        PipeDirection.In);

                uiToCore =
                    CreatePipe(
                        UiToCorePipeName,
                        PipeDirection.Out);

                lock (_sync)
                {
                    _coreToUiServer =
                        coreToUi;

                    _uiToCoreServer =
                        uiToCore;
                }

                UiLog.Info(
                    "Sideron.UI IPC waiting for Core on both pipes.");

                await Task.WhenAll(
                    coreToUi
                        .WaitForConnectionAsync(
                            cancellationToken),
                    uiToCore
                        .WaitForConnectionAsync(
                            cancellationToken));

                var reader =
                    new StreamReader(
                        coreToUi,
                        new UTF8Encoding(
                            false),
                        detectEncodingFromByteOrderMarks:
                            false,
                        bufferSize:
                            4096,
                        leaveOpen:
                            true);

                var writer =
                    new StreamWriter(
                        uiToCore,
                        new UTF8Encoding(
                            false),
                        bufferSize:
                            4096,
                        leaveOpen:
                            true)
                    {
                        AutoFlush = true,
                    };

                lock (_sync)
                {
                    _toCoreWriter =
                        writer;

                    _connected =
                        true;
                }

                ConnectionChanged?.Invoke(
                    true);

                UiLog.Info(
                    "Sideron Core connected to Sideron.UI IPC (2 pipes).");

                await SendAsync(
                    new
                    {
                        type = "hello",
                        source = "ui",
                        version = "3.3.6",
                    });

                while (
                    coreToUi.IsConnected
                    && uiToCore.IsConnected
                    && !cancellationToken
                        .IsCancellationRequested
                )
                {
                    var line =
                        await reader
                            .ReadLineAsync(
                                cancellationToken);

                    if (line is null)
                    {
                        break;
                    }

                    HandleLine(
                        line);
                }
            }
            catch (
                OperationCanceledException
            )
            {
                break;
            }
            catch (Exception exception)
            {
                if (
                    !cancellationToken
                        .IsCancellationRequested
                )
                {
                    UiLog.Error(
                        "Sideron.UI IPC server error.",
                        exception);
                }
            }
            finally
            {
                SetDisconnected();

                lock (_sync)
                {
                    if (
                        ReferenceEquals(
                            _coreToUiServer,
                            coreToUi)
                    )
                    {
                        _coreToUiServer =
                            null;
                    }

                    if (
                        ReferenceEquals(
                            _uiToCoreServer,
                            uiToCore)
                    )
                    {
                        _uiToCoreServer =
                            null;
                    }
                }

                DisposeQuietly(
                    coreToUi);

                DisposeQuietly(
                    uiToCore);
            }

            if (
                !cancellationToken
                    .IsCancellationRequested
            )
            {
                try
                {
                    await Task.Delay(
                        500,
                        cancellationToken);
                }
                catch (
                    OperationCanceledException
                )
                {
                    break;
                }
            }
        }
    }

    private static NamedPipeServerStream CreatePipe(
        string pipeName,
        PipeDirection direction)
    {
        return new NamedPipeServerStream(
            pipeName,
            direction,
            1,
            PipeTransmissionMode.Byte,
            PipeOptions.Asynchronous
            | PipeOptions.CurrentUserOnly);
    }

    private void HandleLine(
        string line)
    {
        try
        {
            using var document =
                JsonDocument.Parse(
                    line);

            var clone =
                document
                    .RootElement
                    .Clone();

            var type =
                TryGetString(
                    clone,
                    "type");

            var name =
                TryGetString(
                    clone,
                    "name");

            UiLog.Info(
                $"IPC Core -> Sideron.UI: type={type ?? "-"}, name={name ?? "-"}");

            MessageReceived?.Invoke(
                clone);
        }
        catch (
            JsonException exception
        )
        {
            UiLog.Error(
                "Invalid IPC JSON received.",
                exception);
        }
    }

    private async Task<bool> SendAsync(
        object message)
    {
        StreamWriter?
            writer;

        lock (_sync)
        {
            writer =
                _connected
                    ? _toCoreWriter
                    : null;
        }

        if (writer is null)
        {
            return false;
        }

        await _sendLock
            .WaitAsync();

        try
        {
            var json =
                JsonSerializer.Serialize(
                    message);

            await writer
                .WriteLineAsync(
                    json);

            await writer
                .FlushAsync();

            return true;
        }
        catch (
            IOException exception
        )
        {
            UiLog.Error(
                "Sideron.UI IPC write failed.",
                exception);

            SetDisconnected();

            return false;
        }
        catch (
            ObjectDisposedException
        )
        {
            SetDisconnected();

            return false;
        }
        finally
        {
            _sendLock.Release();
        }
    }

    private void SetDisconnected()
    {
        var notify =
            false;

        lock (_sync)
        {
            if (_connected)
            {
                notify =
                    true;
            }

            _connected =
                false;

            _toCoreWriter =
                null;
        }

        if (notify)
        {
            UiLog.Info(
                "Sideron Core disconnected from Sideron.UI IPC.");

            ConnectionChanged?.Invoke(
                false);
        }
    }

    private static string? TryGetString(
        JsonElement element,
        string propertyName)
    {
        if (
            element.ValueKind
                == JsonValueKind.Object
            && element.TryGetProperty(
                propertyName,
                out var node)
            && node.ValueKind
                == JsonValueKind.String
        )
        {
            return node.GetString();
        }

        return null;
    }

    private static void DisposeQuietly(
        IDisposable? disposable)
    {
        try
        {
            disposable?.Dispose();
        }
        catch
        {
            // Nothing to do.
        }
    }

    public void Dispose()
    {
        CancellationTokenSource?
            cancellation;

        NamedPipeServerStream?
            coreToUi;

        NamedPipeServerStream?
            uiToCore;

        lock (_sync)
        {
            cancellation =
                _cancellation;

            _cancellation =
                null;

            coreToUi =
                _coreToUiServer;

            uiToCore =
                _uiToCoreServer;

            _coreToUiServer =
                null;

            _uiToCoreServer =
                null;

            _toCoreWriter =
                null;

            _connected =
                false;
        }

        try
        {
            cancellation?.Cancel();
        }
        catch
        {
            // Nothing to do.
        }

        DisposeQuietly(
            coreToUi);

        DisposeQuietly(
            uiToCore);

        cancellation?.Dispose();

        _sendLock.Dispose();
    }
}
