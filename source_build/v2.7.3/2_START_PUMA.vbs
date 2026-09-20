Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = folder & "\.venv\Scripts\pythonw.exe"
app = folder & "\app.py"
If fso.FileExists(pythonw) Then
    shell.CurrentDirectory = folder
    shell.Run Chr(34) & pythonw & Chr(34) & " " & Chr(34) & app & Chr(34), 0, False
Else
    MsgBox "PUMA 설치가 아직 완료되지 않았습니다." & vbCrLf & vbCrLf & "먼저 1_SETUP.bat 를 더블클릭해 주세요.", 48, "PUMA STOCK PRO"
End If
