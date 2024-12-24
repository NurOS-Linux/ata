import os
import struct
import zstandard as zstd
import click
from pathlib import Path

# Формат ATA:
# Header: "ATA1" (4 bytes) - магическая подпись
# Number of files (4 bytes)
# Per file:
#   Filename length (2 bytes)
#   Filename (variable)
#   File size (8 bytes)
#   Compressed size (8 bytes)
#   File data (compressed)

def write_ata_header(f, num_files):
    """Записать заголовок ATA"""
    f.write(b"ATA1")  # Магическая подпись
    f.write(struct.pack("<I", num_files))  # Количество файлов

def write_file_header(f, filename, file_size, compressed_size):
    """Записать заголовок файла"""
    name_bytes = filename.encode('utf-8')
    f.write(struct.pack("<H", len(name_bytes)))  # Длина имени файла
    f.write(name_bytes)  # Имя файла
    f.write(struct.pack("<Q", file_size))  # Размер файла
    f.write(struct.pack("<Q", compressed_size))  # Сжатый размер

def read_ata_header(f):
    """Прочитать заголовок ATA"""
    magic = f.read(4)
    if magic != b"ATA1":
        raise ValueError("Invalid ATA format")
    return struct.unpack("<I", f.read(4))[0]  # Количество файлов

def read_file_header(f):
    """Прочитать заголовок файла"""
    name_len = struct.unpack("<H", f.read(2))[0]
    filename = f.read(name_len).decode('utf-8')
    file_size = struct.unpack("<Q", f.read(8))[0]
    compressed_size = struct.unpack("<Q", f.read(8))[0]
    return filename, file_size, compressed_size

@click.group()
def main():
    """AnmiTali Archive - Modern Terminal Archiver"""
    pass

@main.command()
@click.argument('archive_name', type=click.Path())
@click.argument('files', nargs=-1, type=str)
@click.option('-c', '--compression', type=click.Choice(['zstd', 'none']), default='zstd', 
              help='Compression method')
@click.option('-l', '--level', type=int, default=3, 
              help='Compression level (1-19)')
@click.option('-v', '--verbose', is_flag=True, 
              help='Verbose output')
def create(archive_name, files, compression, level, verbose):
    """Create new archive"""
    if not files:
        click.echo("Error: No files specified")
        return

    # Проверяем существование файлов
    valid_files = []
    for file_path in files:
        if not os.path.exists(file_path):
            click.echo(f"Warning: Skipping non-existent file: {file_path}")
            continue
        valid_files.append(file_path)

    if not valid_files:
        click.echo("Error: No valid files to archive")
        return

    try:
        with open(archive_name, 'wb') as archive:
            # Записываем заголовок архива
            write_ata_header(archive, len(valid_files))
            
            # Создаем компрессор
            cctx = zstd.ZstdCompressor(level=level) if compression == 'zstd' else None

            # Обрабатываем каждый файл
            for file_path in valid_files:
                if verbose:
                    click.echo(f"Adding: {file_path}")

                # Читаем исходный файл
                with open(file_path, 'rb') as f:
                    data = f.read()
                    file_size = len(data)

                # Сжимаем если нужно
                if compression == 'zstd':
                    compressed = cctx.compress(data)
                else:
                    compressed = data

                # Записываем заголовок файла
                write_file_header(archive, os.path.basename(file_path), 
                                file_size, len(compressed))
                
                # Записываем данные
                archive.write(compressed)

        if verbose:
            click.echo(f"Archive created successfully: {archive_name}")

    except Exception as e:
        click.echo(f"Error creating archive: {e}")

@main.command()
@click.argument('archive_name', type=click.Path(exists=True))
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def list(archive_name, verbose):
    """List archive contents"""
    try:
        with open(archive_name, 'rb') as archive:
            num_files = read_ata_header(archive)
            
            for _ in range(num_files):
                filename, file_size, compressed_size = read_file_header(archive)
                if verbose:
                    click.echo(f"{filename} (Original: {file_size} bytes, "
                             f"Compressed: {compressed_size} bytes)")
                else:
                    click.echo(filename)
                archive.seek(compressed_size, 1)  # Пропускаем данные файла

    except Exception as e:
        click.echo(f"Error listing archive: {e}")

@main.command()
@click.argument('archive_name', type=click.Path(exists=True))
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def extract(archive_name, verbose):
    """Extract archive contents"""
    try:
        with open(archive_name, 'rb') as archive:
            num_files = read_ata_header(archive)
            dctx = zstd.ZstdDecompressor()

            for _ in range(num_files):
                filename, file_size, compressed_size = read_file_header(archive)
                
                if verbose:
                    click.echo(f"Extracting: {filename}")

                # Читаем сжатые данные
                compressed_data = archive.read(compressed_size)

                # Распаковываем и сохраняем
                try:
                    data = dctx.decompress(compressed_data)
                except:
                    data = compressed_data  # Файл не был сжат

                with open(filename, 'wb') as f:
                    f.write(data)

        if verbose:
            click.echo("Extraction completed successfully")

    except Exception as e:
        click.echo(f"Error extracting archive: {e}")

@main.command()
@click.argument('archive_name', type=click.Path(exists=True))
@click.option('-v', '--verbose', is_flag=True, help='Verbose output')
def verify(archive_name, verbose):
    """Verify archive integrity"""
    try:
        with open(archive_name, 'rb') as archive:
            # Проверяем заголовок
            try:
                num_files = read_ata_header(archive)
            except:
                click.echo("Invalid archive header")
                return

            if verbose:
                click.echo(f"Archive contains {num_files} files")

            # Проверяем каждый файл
            dctx = zstd.ZstdDecompressor()
            for i in range(num_files):
                try:
                    filename, file_size, compressed_size = read_file_header(archive)
                    if verbose:
                        click.echo(f"Verifying: {filename}")
                    
                    # Читаем и проверяем сжатые данные
                    compressed_data = archive.read(compressed_size)
                    try:
                        data = dctx.decompress(compressed_data)
                        if len(data) != file_size:
                            raise ValueError(f"Size mismatch for {filename}")
                    except zstd.ZstdError:
                        # Возможно файл не был сжат
                        if len(compressed_data) != file_size:
                            raise ValueError(f"Size mismatch for {filename}")
                except Exception as e:
                    click.echo(f"Error in file {filename}: {e}")
                    return

            click.echo("Archive is valid")

    except Exception as e:
        click.echo(f"Archive verification failed: {e}")

if __name__ == "__main__":
    main()
