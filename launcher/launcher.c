#include <windows.h>
#include <wchar.h>
/* Запускає runtime\pythonw.exe app\shorts.py з папки, де лежить exe. */
int WINAPI wWinMain(HINSTANCE h, HINSTANCE p, PWSTR cmd, int show) {
    wchar_t dir[4096], line[16384];
    DWORD n = GetModuleFileNameW(NULL, dir, 4096);
    while (n && dir[n - 1] != L'\\') n--;
    dir[n] = 0;
    _snwprintf(line, 16384, L"\"%sruntime\\pythonw.exe\" \"%sapp\\shorts.py\"", dir, dir);
    STARTUPINFOW si = {sizeof si};
    PROCESS_INFORMATION pi;
    if (!CreateProcessW(NULL, line, NULL, NULL, FALSE, 0, NULL, dir, &si, &pi)) {
        MessageBoxW(NULL, L"Не вдалося запустити runtime\\pythonw.exe.\nПеревір, що папка програми розпакована повністю.", L"ShortsMaker", MB_ICONERROR);
        return 1;
    }
    CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
    return 0;
}
