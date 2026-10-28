import Foundation
import Darwin

/// A live shell alone is idle. Foreground, stopped and background children are work.
enum TerminalActivity {
    static func hasJobs(shellPID: pid_t, terminalFD: Int32) -> Bool {
        guard shellPID > 0, kill(shellPID, 0) == 0 else { return false }
        let foreground = tcgetpgrp(terminalFD)
        let shellGroup = getpgid(shellPID)
        if foreground > 0, foreground != shellGroup, kill(-foreground, 0) == 0 { return true }
        var children = [pid_t](repeating: 0, count: 64)
        let count = children.withUnsafeMutableBytes { proc_listchildpids(shellPID, $0.baseAddress, Int32($0.count)) }
        if count < 0 { return true } // Don't silently end a session we couldn't inspect.
        for child in children.prefix(min(children.count, Int(count))) where child > 0 {
            var info = proc_bsdinfo()
            let size = Int32(MemoryLayout<proc_bsdinfo>.size)
            let read = proc_pidinfo(child, PROC_PIDTBSDINFO, 0, &info, size)
            if read == size {
                if info.pbi_status != UInt32(SZOMB) { return true }
            } else if kill(child, 0) == 0 { return true }
        }
        return false
    }
}
