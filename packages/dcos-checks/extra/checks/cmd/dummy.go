// Copyright © 2017 Mesosphere Inc. <http://mesosphere.com>
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package cmd

import (
	"fmt"
	"os"
	"strconv"

	"github.com/sirupsen/logrus"
	"github.com/spf13/cobra"
)

// dummyCmd represents the dummy command
var dummyCmd = &cobra.Command{
	Use:   "dummy",
	Short: "A brief description of your command",
	Long: `A longer description that spans multiple lines and likely contains examples
and usage of using your command. For example:

Cobra is a CLI library for Go that empowers applications.
This application is a tool to generate the needed files
to quickly create a Cobra application.`,
	Run: func(cmd *cobra.Command, args []string) {
		var (
			returnCode int
			err error
		)

		msg := map[int]string{0: "SUCCESS", 1: "WARNING", 2: "FAILURE"}
		if len(args) != 0 {
			returnCode, err = strconv.Atoi(args[0])
			if err != nil {
				logrus.Fatalf("dummy argument must be integer got %s: %s", args[0], err)
			}
		}

		if message, ok := msg[returnCode]; ok {
			fmt.Println(message)
		}
		os.Exit(returnCode)
	},
}

func init() {
	RootCmd.AddCommand(dummyCmd)
}
