package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"os/signal"
	"path/filepath"
	"syscall"
)

func executeAndPassthrough(stdinStr string, binary string, args []string) (int, error) {
	cmd := exec.Command(binary, args...)
	cmd.Stderr = os.Stderr
	cmd.Stdout = os.Stdout
	cmd.Env = os.Environ()

	stdin, err := cmd.StdinPipe()
	if err != nil {
		return 0, err
	}

	// Start subprocess
	if err := cmd.Start(); err != nil {
		stdin.Close()
		return 0, err
	}

	// Forward interrupt signals to the launched process
	sigs := make(chan os.Signal, 1)
	signal.Notify(sigs, syscall.SIGINT, syscall.SIGTERM)
	go func() {
		for {
			sig := <-sigs
			if cmd.ProcessState != nil && cmd.ProcessState.Exited() {
				return
			}
			cmd.Process.Signal(sig)
		}
	}()

	// Send STDIN and release
	io.WriteString(stdin, stdinStr)
	stdin.Close()

	// Wait until the command is completed and remove the signal handlers
	err = cmd.Wait()
	signal.Reset(syscall.SIGINT, syscall.SIGTERM)
	sigs <- syscall.SIGINT

	if err != nil {
		// Get exit code on non-zero exits
		if exiterr, ok := err.(*exec.ExitError); ok {
			if status, ok := exiterr.Sys().(syscall.WaitStatus); ok {
				return status.ExitStatus(), nil
			}
		} else {
			return 0, err
		}
	}

	return 0, nil
}

func parseStdinJSONMap() (map[string]interface{}, error) {
	dst := make(map[string]interface{})

	// Don't block on waiting for STDIN if there are no data to read from
	stat, _ := os.Stdin.Stat()
	if (stat.Mode() & os.ModeCharDevice) != 0 {
		return dst, nil
	}

	buf := new(bytes.Buffer)
	buf.ReadFrom(os.Stdin)

	err := json.Unmarshal(buf.Bytes(), &dst)
	if err != nil {
		return nil, err
	}

	return dst, nil
}

func compressLongLabel(str string) string {
	h := sha256.New()
	h.Write([]byte(str))

	hash := fmt.Sprintf("%x", h.Sum(nil))
	lastPart := str[len(str)-53:]

	return fmt.Sprintf("%s...%s", hash[0:7], lastPart)
}

func compressLabels(labels []map[string]interface{}) []map[string]interface{} {
	for _, kv := range labels {
		if value, ok := kv["value"]; ok {
			if valueStr, ok := value.(string); ok {
				if len(valueStr) > 63 {
					kv["value"] = compressLongLabel(valueStr)
				}
			}
		}
	}
	return labels
}

func compressMesosArgsConfig(config map[string]interface{}) map[string]interface{} {
	//
	// We are manually parsing the mesos args interface, as defined here:
	// http://mesos.apache.org/documentation/latest/cni/#passing-network-labels-and-port-mapping-information-to-cni-plugi

	// .args{}
	if argsMapIface, ok := config["args"]; ok {
		if argsMap, ok := argsMapIface.(map[string]interface{}); ok {
			// .args."org.apache.mesos"{}
			if mesosMapIface, ok := argsMap["org.apache.mesos"]; ok {
				if mesosMap, ok := mesosMapIface.(map[string]interface{}); ok {
					// .args."org.apache.mesos".network_info{}
					if netInfoMapIface, ok := mesosMap["network_info"]; ok {
						if netInfoMap, ok := netInfoMapIface.(map[string]interface{}); ok {
							// .args."org.apache.mesos".network_info.labels{}
							if labelsMapIface, ok := netInfoMap["labels"]; ok {
								if labelsMap, ok := labelsMapIface.(map[string]interface{}); ok {
									// .args."org.apache.mesos".network_info.labels.labels[]
									if labelsSliceIface, ok := labelsMap["labels"]; ok {
										if labelsSlice, ok := labelsSliceIface.([]interface{}); ok {

											// Convert interface to map labels and compress
											var labelMapArray []map[string]interface{} = nil
											for _, val := range labelsSlice {
												if v, ok := val.(map[string]interface{}); ok {
													labelMapArray = append(labelMapArray, v)
												}
											}

											labelsMap["labels"] = compressLabels(labelMapArray)
										}
									}
								}
							}
						}
					}
				}
			}
		}
	}

	return config
}

func main() {
	dir, err := filepath.Abs(filepath.Dir(os.Args[0]))
	if err != nil {
		panic(fmt.Errorf("Could not compute current path: %s", err.Error()))
	}

	// Assume that the actual plugin we are wrapping is located at the
	// current directory as the current binary, suffixed with `-impl`
	cniPluginPath := filepath.Join(dir, fmt.Sprintf("%s-impl", filepath.Base(os.Args[0])))
	if _, err := os.Stat(cniPluginPath); os.IsNotExist(err) {
		panic(fmt.Errorf("Could not find calico CNI implementation plugin on %s", cniPluginPath))
	}

	// We are parsing STDIN as a generic JSON object and not as a structured
	// object in order to leave fields we don't know (and care) untouched.
	cfg, err := parseStdinJSONMap()
	if err != nil {
		panic(fmt.Errorf("Error parsing STDIN as JSON: %s", err.Error()))
	}

	// Locate `args/org.apache.mesos/network_info` and compress labels
	cfg = compressMesosArgsConfig(cfg)

	// Convert map back to a string
	stdin, err := json.Marshal(cfg)
	if err != nil {
		panic(fmt.Errorf("Could not marshal-back the JSON input: %s", err.Error()))
	}

	// Call-out to the CNI plugin
	ret, err := executeAndPassthrough(string(stdin), cniPluginPath, os.Args[1:])
	if err != nil {
		panic(fmt.Errorf("Could not execute CNI plugin: %s", err.Error()))
	}

	os.Exit(ret)
}
