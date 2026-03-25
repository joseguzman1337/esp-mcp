"""
Utility functions for ESP-IDF tools
"""
import os
import asyncio
from typing import Optional, Tuple


async def run_command_async(command: str) -> Tuple[int, str, str]:
    """Run a command asynchronously and capture output

    Args:
        command: The command to run

    Returns:
        Tuple[int, str, str]: Return code, stdout, stderr
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        return process.returncode, stdout.decode(), stderr.decode()
    except Exception as e:
        return 1, "", f"Error executing command: {str(e)}"

async def run_command_async_stream(command: str, log_path: str) -> Tuple[int, str, str]:
    """Run a command asynchronously, streaming stdout/stderr to a log file.

    Args:
        command: The command to run
        log_path: Path to log file for real-time output

    Returns:
        Tuple[int, str, str]: Return code, stdout, stderr
    """
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout_chunks = []
        stderr_chunks = []

        async def _read_stream(stream, prefix, chunks):
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode(errors="replace")
                chunks.append(text)
                with open(log_path, "a") as handle:
                    handle.write(f"{prefix}{text}")
                    handle.flush()

        await asyncio.gather(
            _read_stream(process.stdout, "[stdout] ", stdout_chunks),
            _read_stream(process.stderr, "[stderr] ", stderr_chunks),
        )

        returncode = await process.wait()
        return returncode, "".join(stdout_chunks), "".join(stderr_chunks)
    except Exception as e:
        return 1, "", f"Error executing command: {str(e)}"

def get_esp_idf_dir(idf_path: str = None) -> str:
    """Get the ESP-IDF directory path

    Args:
        idf_path: Optional path to ESP-IDF directory. If None or empty, uses IDF_PATH environment variable.

    Returns:
        str: Path to the ESP-IDF directory

    Raises:
        ValueError: If idf_path is not provided and IDF_PATH environment variable is not set
    """
    if idf_path:
        return idf_path
    if "IDF_PATH" in os.environ:
        return os.environ["IDF_PATH"]
    raise ValueError("IDF_PATH must be provided either as parameter or environment variable")

def get_export_script(idf_path: str = None) -> str:
    """Get the path to the ESP-IDF export script

    Args:
        idf_path: Optional path to ESP-IDF directory. If None or empty, uses IDF_PATH environment variable.

    Returns:
        str: Path to the export script
    """
    return os.path.join(get_esp_idf_dir(idf_path), "export.sh")

def check_esp_idf_installed(idf_path: str = None) -> bool:
    """Check if ESP-IDF is installed

    Args:
        idf_path: Optional path to ESP-IDF directory. If None or empty, uses IDF_PATH environment variable.

    Returns:
        bool: True if ESP-IDF is installed, False otherwise
    """
    try:
        return os.path.exists(get_esp_idf_dir(idf_path))
    except ValueError:
        return False

async def list_serial_ports(vid: Optional[int] = None, pid: Optional[int] = None) -> Tuple[int, str, str]:
    """List available serial ports for ESP devices

    Args:
        vid: Optional USB vendor ID to filter by.
        pid: Optional USB product ID to filter by.

    Returns:
        Tuple[int, str, str]: Return code, stdout with port list, stderr
    """
    try:
        try:
            from serial.tools import list_ports
        except Exception as e:
            # Fall back to subprocess if pyserial isn't importable in this environment.
            process = await asyncio.create_subprocess_shell(
                "python -m serial.tools.list_ports",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate()
            return process.returncode, stdout.decode(), stderr.decode()

        ports = list(list_ports.comports())
        esp_vid = 0x303A

        if vid is not None:
            ports = [p for p in ports if p.vid == vid]
        if pid is not None:
            ports = [p for p in ports if p.pid == pid]

        if vid is None and pid is None:
            # Prefer Espressif USB-C CDC ports first; fall back to other serial ports.
            def _port_rank(port):
                dev = (port.device or "").lower()
                is_esp = port.vid == esp_vid
                is_usb_cdc = "usbmodem" in dev or "ttyacm" in dev
                return (0 if is_esp and is_usb_cdc else 1 if is_esp else 2, dev)

            ports.sort(key=_port_rank)

        lines = []
        for port in ports:
            vid_str = f"0x{port.vid:04x}" if port.vid is not None else "unknown"
            pid_str = f"0x{port.pid:04x}" if port.pid is not None else "unknown"
            desc = port.description or ""
            lines.append(f"{port.device}\tvid={vid_str} pid={pid_str} {desc}".rstrip())

        if not lines:
            return 0, "", "No serial ports matched the requested filter."

        return 0, "\n".join(lines) + "\n", ""
    except Exception as e:
        # Fallback: try common port patterns
        common_ports = ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "/dev/ttyACM1",
                       "/dev/cu.usbserial-*", "/dev/cu.SLAB_USBtoUART", "COM1", "COM2", "COM3"]
        port_info = "Common ESP device ports to try:\n" + "\n".join(common_ports)
        return 0, port_info, f"Note: Could not auto-detect ports. Error: {str(e)}"
