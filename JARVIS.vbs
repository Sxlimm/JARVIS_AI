Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")

Dossier = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = Dossier

' pyw = lanceur Python sans fenetre ; fonctionne sur n'importe quel PC ou Python est installe
WshShell.Run "pyw """ & Dossier & "\jarvis.py""", 0, False
