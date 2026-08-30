param(
    [string]$WakeWord = "SIDERON",
    [string]$Culture = "fr-FR",
    [double]$MinConfidence = 0.55
)

$ErrorActionPreference = "Stop"

try {
    Add-Type -AssemblyName System.Speech
}
catch {
    Write-Output "ERROR|SYSTEM_SPEECH_UNAVAILABLE|$($_.Exception.Message)"
    exit 10
}

try {
    $recognizers = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()

    if ($null -eq $recognizers -or $recognizers.Count -eq 0) {
        Write-Output "ERROR|NO_RECOGNIZER|No Windows speech recognizer is installed."
        exit 11
    }

    $selected = $recognizers |
        Where-Object { $_.Culture.Name -ieq $Culture } |
        Select-Object -First 1

    if ($null -eq $selected) {
        $languagePrefix = ($Culture -split "-")[0]

        $selected = $recognizers |
            Where-Object {
                $_.Culture.TwoLetterISOLanguageName -ieq $languagePrefix
            } |
            Select-Object -First 1
    }

    if ($null -eq $selected) {
        Write-Output "ERROR|CULTURE_NOT_FOUND|No compatible Windows speech recognizer for $Culture."
        exit 12
    }

    $engine = New-Object System.Speech.Recognition.SpeechRecognitionEngine($selected.Id)

    $choices = New-Object System.Speech.Recognition.Choices
    $choices.Add($WakeWord)

    $builder = New-Object System.Speech.Recognition.GrammarBuilder
    $builder.Culture = $selected.Culture
    $builder.Append($choices)

    $grammar = New-Object System.Speech.Recognition.Grammar($builder)
    $grammar.Name = "SideronWakeWord"

    $engine.LoadGrammar($grammar)

    $engine.InitialSilenceTimeout = [TimeSpan]::FromSeconds(5)
    $engine.BabbleTimeout = [TimeSpan]::FromSeconds(5)
    $engine.EndSilenceTimeout = [TimeSpan]::FromMilliseconds(250)
    $engine.EndSilenceTimeoutAmbiguous = [TimeSpan]::FromMilliseconds(400)

    $engine.SetInputToDefaultAudioDevice()

    Write-Output "READY|$($selected.Culture.Name)|$WakeWord"
    [Console]::Out.Flush()

    while ($true) {
        try {
            $result = $engine.Recognize(
                [TimeSpan]::FromSeconds(5)
            )

            if ($null -eq $result) {
                continue
            }

            $text = [string]$result.Text
            $confidence = [double]$result.Confidence

            if (
                $text -ieq $WakeWord -and
                $confidence -ge $MinConfidence
            ) {
                $confidenceText = $confidence.ToString(
                    "0.000",
                    [System.Globalization.CultureInfo]::InvariantCulture
                )

                Write-Output "WAKE|$confidenceText|$text"
                [Console]::Out.Flush()
            }
        }
        catch [System.OperationCanceledException] {
            continue
        }
        catch {
            Write-Output "WARN|RECOGNIZE|$($_.Exception.Message)"
            [Console]::Out.Flush()
            Start-Sleep -Milliseconds 250
        }
    }
}
catch {
    Write-Output "ERROR|STARTUP|$($_.Exception.Message)"
    exit 20
}
finally {
    if ($null -ne $engine) {
        try { $engine.Dispose() } catch {}
    }
}
